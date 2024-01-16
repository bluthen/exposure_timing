# Exposure Timing - NEXTA Analysis
# Copyright (C) 2024 Russell Valentine
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from astropy.io import fits
import json
import cv2
import numpy as np
from auto_stretch.stretch import Stretch


def scale_imshow(name, img, scale, interpolation=cv2.INTER_AREA):
    """
    Like cv2.imshow, but scaled. Uses opencv to show a scaled version of a image.
    :param name: Window name
    :param img: Image to show scaled
    :param scale: value < 1 for smaller > 1 for bigger
    :param interpolation: What kind of interpolation to do in the resize.
    :return:
    """
    rimg = img.copy()
    if rimg.dtype == np.bool_:
        rimg = np.uint8(rimg) * 255
    rmax = rimg.max()
    rmin = rimg.min()
    rimg = np.uint8(255 * ((rimg - rmin) / (rmax - rmin)))
    rimg = cv2.resize(rimg, (0, 0), fx=scale, fy=scale, interpolation=interpolation)
    cv2.imshow(name, rimg)


def get_poly_values(fitsimg, poly):
    """
    Get the values from an image inside a polygon
    :param fitsimg:
    :param poly:
    :return:
    """
    # https://stackoverflow.com/questions/60964249/how-to-check-the-color-of-pixels-inside-a-polygon-and-remove-the-polygon-if-it-c
    # https://stackoverflow.com/questions/30901019/extracting-polygon-given-coordinates-from-an-image-using-opencv
    # rayryeng
    mask = get_poly_mask(fitsimg, poly)
    out = np.zeros_like(fitsimg)
    out[mask] = fitsimg[mask]
    # print(fitsimg[mask])
    # scale_imshow('Test', cv2.threshold(out, 1, 1, cv2.THRESH_BINARY)[1], 0.5)
    # cv2.waitKey(0)
    return fitsimg[mask]


def get_poly_mask(img, poly):
    """
    Get inverse mask of a polygon.
    :param img: Image with same size we want our mask.
    :param poly: The polygon we want to accept
    :return: mask
    """
    poly = np.int32(np.array(poly, dtype=np.int32))
    # print('poly', poly, poly.dtype)
    mask = np.zeros_like(img)
    cv2.fillPoly(mask, np.int32([poly]), 1)
    mask = mask > 0
    # scale_imshow('Test', mask, 0.5)
    # cv2.waitKey(0)
    return mask


def decode_nexta_digit(digit):
    """
    Decodes a NEXTA digit (4 leds)
    :param digit: 1 or on 0 for off
    :return: Number decode, or if invalide then '?'
    :rtype: int | str
    """
    if digit == '0000':
        return 0
    elif digit == '0001':
        return 1
    elif digit == '0010':
        return 2
    elif digit == '0100':
        return 3
    elif digit == '1000':
        return 4
    elif digit == '0011':
        return 5
    elif digit == '0110':
        return 6
    elif digit == '1100':
        return 7
    elif digit == '0111':
        return 8
    elif digit == '1111':
        return 9
    else:
        return '?'


def nexta_check_error(sled_values):
    """
    Checks if values are a known error code
    :param sled_values:
    :return: If error code and a error message that goes with it
    :rtype: bool, str
    """
    if sled_values == '00000000000000000000':
        return True, 'Powered off'
    elif sled_values == '10100000000000000000':
        return True, 'Internal clock drift too large'
    elif sled_values == '10101000000000000000':
        return True, 'GNSS signal lost'
    elif sled_values == '10101010000000000000':
        return True, 'Initial setup - waiting for GNSS fix'
    elif sled_values == '10101010100000000000':
        return True, 'Initial setup - measuring internal clock drift'
    elif sled_values == '10101010101000000000':
        return True, 'Initial setup - finished'
    else:
        return False, ''


def booleanlist_to_string(ourlist, truechar='1', falsechar='0'):
    """
    Given a boolean list turns it to a string of truechar, or falsechar.
    :param ourlist: A list
    :param truechar:
    :param falsechar:
    :return:
    :rtype: str
    """
    ourstr = ''
    for i in ourlist:
        if i:
            ourstr += truechar
        else:
            ourstr += falsechar
    return ourstr


def decode_nexta_time(led_values):
    """
    Decodes full array of LED values into a time value.
    :param led_values:
    :return: value, led_count, err (maybe least significant figure, exponent)
    :rtype: Dict
    """
    decoded = ''
    sled_values = booleanlist_to_string(led_values).ljust(20, '0')
    err, reason = nexta_check_error(sled_values)
    if err:
        return None
    for i in range(0, len(sled_values), 4):
        digit = str(decode_nexta_digit(sled_values[i:i + 4]))
        if digit == '?':
            err = max(-1 * int(len(led_values) / 4.0), -1 * i)
            return {'value': decoded, 'err': err, 'led_count': len(led_values),
                    'lsb': booleanlist_to_string(list(led_values[i:]))}
        decoded += digit
        if i == 0:
            decoded += '.'
    err = -1 * int(len(led_values) / 4.0)
    return {'value': decoded, 'led_count': len(led_values), 'err': err}


def get_led_on_threshold(rois, stretched_image, dscale, verbose=0):
    """
    Tries to get value that if greater than the LED is considered on versus off.
    :param rois: Polygons where our LEDs are in the image.
    :param stretched_image:
    :param dscale:
    :param verbose:
    :return:
    :rtype: float
    """
    # Lets get our background to know what is off vs on.
    # TODO: Because of vignetting and possible gradients a better way to know if led on or off, if we support led off frame taken at same exposure time
    # TODO: Would help for reading area where exposure is greater than blinking rate as well.
    background = []
    for roi in rois:
        background.extend(get_poly_values(stretched_image, roi).tolist())
    background = np.array(background).flatten()
    led_on_thresh = background.mean()
    if verbose >= 1:
        print('Background Mean: ', led_on_thresh)
    if verbose >= 2:
        led_thresh = cv2.threshold(stretched_image, led_on_thresh, 255, cv2.THRESH_BINARY)[1]
        led_thresh = cv2.cvtColor(led_thresh, cv2.COLOR_GRAY2BGR)
        for poly in rois:
            cv2.polylines(led_thresh, [np.int32(poly)], True, (255, 0, 0), 2)
        if verbose >= 2:
            scale_imshow('debug', led_thresh, dscale)
            cv2.waitKey(1)
    return led_on_thresh


def get_y_roi_range(rois, verbose):
    """
    We only need to loop through rows that have the LEDs, so lets find max, min, y rows in our roi
    :param rois: Our region of interest (polygon where LEDs are in the image).
    :param verbose:
    :return: y_min, y_max
    :rtype: List[int]
    """

    ys = []
    for roi in rois:
        yy = list(zip(*roi))
        ys.append(max(yy[1]))
        ys.append(min(yy[1]))
    y_min = min(ys)
    y_max = max(ys) + 1
    if verbose >= 1:
        print('y range:', y_min, y_max)
    return y_min, y_max


def get_timing_led_rows(y_min, y_max, stretched_image, led_on_thresh, rois, verbose=0):
    """
    For rows with LEDS array if leds are on.
    :param y_min: Lower bound of rows to check
    :param y_max: Greater bound of rows to check
    :param stretched_image: Our image stretched
    :param led_on_thresh: Value that if greater indicate LED is on verses off
    :param rois: Regions of interest (polygons of leds)
    :param verbose: How much debugging output to do
    :return: A dictionary with row y as key, and value being a list of if LED is on or of 0 or 1
    :rtype: Dict[int, List[bool]] = List[bool]
    """
    timed_rows = {}
    # For each row with LED in it
    for y in range(y_min, y_max):
        if verbose >= 1:
            if y % 50 == 0:
                print('Checking Row', y, end='\r')

        # Get the values of our the intersection of the line and roi poly
        # TODO: Might be faster is just the row of values roi masked
        linemask = np.zeros_like(stretched_image)
        linemask[y] = np.ones(stretched_image.shape[1])
        linemask = linemask > 0
        row_led_in = []
        row_led_on = []
        for roi_idx in range(len(rois) - 1):
            # For each point if row is in the poly.
            poly_mask = get_poly_mask(stretched_image, rois[roi_idx])
            and_mask = np.logical_and(linemask, poly_mask)
            # Is LED on row
            in_row = np.any(and_mask)
            row_led_in.append(in_row)
            if in_row:
                poly_values = stretched_image[and_mask]
                pmean = poly_values.mean()
                digit_led = pmean > led_on_thresh
                row_led_on.append(digit_led)
            else:
                break
        # If we have at least 12 that is some value to us
        if sum(row_led_in) >= 12:
            timed_rows[y] = row_led_on
    if verbose >= 1:
        print()
        print('Possible timing rows: '+str(len(timed_rows.keys()))+'/'+str(y_max-y_min))
    return timed_rows


def filter_outliers(timed_rows, fits_header_nextatime, verbose=0):
    """
    Filter outliers likely on the top and bottom rows of our roi where roi is slight off our LEDs, or image too noisy
    :param timed_rows: Timing data
    :param fits_header_nextatime:
    :param verbose: How much debug output to do.
    :return: Cleaner timed rows.
    """
    # TODO: This is a mess, clean it up, bad rows can decode valid often.
    orig_row_count = len(timed_rows.keys())

    # Difference between rows is too great, likely missing seconds LEDs
    # First lets see if we are increasing or decreasing as y increases
    last_y_value = None
    delta_t = []
    vs = []
    possible_wraps = [False, False]
    for y in timed_rows.keys():
        v = float(timed_rows[y]['value'])
        vs.append(v)
        if v < 0.2:
            possible_wraps[0] = True
        if v > 9.8:
            possible_wraps[1] = True
        if last_y_value is not None:
            delta_t.append(last_y_value - v)
        last_y_value = v
    delta_t = np.array(delta_t)
    increasing = (delta_t > 0).sum() > (delta_t < 0).sum()


    # Find mean time adjusted for 10s wrap
    vs = []
    wrapped = False
    mean_v = None
    to_del = []
    for i in range(2):
        for y in timed_rows.keys():
            v = float(timed_rows[y]['value'])
            orig_v = v
            if last_y_value:
                if increasing:
                    if wrapped and v < 1.0:
                        v += 10
                    elif last_y_value > 9.8 and v < 0.2:
                        v += 10
                        wrapped = True
                    else:
                        wrapped = False
                else:
                    if wrapped and v > 9.0:
                        v -= 10
                    if last_y_value < 0.2 and v > 9.8:
                        v -= 10
                        wrapped = True
                    else:
                        wrapped = False
            vs.append(v)
            if mean_v is not None:
                if abs(v - mean_v) > 1.0:
                    to_del.append(y)
            last_y_value = orig_v
        mean_v = np.array(vs).mean()
        print(mean_v)

    deleted_from_mean = len(to_del)
    for y in to_del:
        del timed_rows[y]

    # We can do better but for now we'll just throw out any non-monotonic inc or dec
    last_y_value = None
    to_del = []
    for y in timed_rows.keys():
        v = float(timed_rows[y]['value'])
        orig_v = v
        if last_y_value is not None:
            if increasing:
                if last_y_value > 9.8 and v < 0.2:
                    v += 10
            else:
                if last_y_value < 0.2 and v > 9.8:
                    v -= 10
            delta_t = last_y_value - v
            # print(y, delta_t)
            if increasing and delta_t < 0 or not increasing and delta_t > 0:
                to_del.append(y)
        last_y_value = orig_v

    deleted_non_monotonic = len(to_del)
    for y in to_del:
        del timed_rows[y]

    if verbose >= 1:
        print('Filtered rows: ', orig_row_count - len(timed_rows.keys()), 'because mean:', deleted_from_mean, 'because non-monotonic', deleted_non_monotonic)
    return timed_rows, increasing


def calculate_stats(timed_rows, increasing, rows, fits_header_nextatime, verbose=0):
    """
    Tries to calculates some statistics about our timing, like how off the fits timestamp is, rolling shutter roll readout time, etc.
    :param timed_rows:
    :param increasing:
    :param rows:
    :param fits_header_nexatime:
    :param verbose:
    :return: Dict[str, float]
    """

    # TODO: Even with exposure times greater than 10uS we should be able to infer some timing info
    # TODO: about rolling shutter by rows of 10^-5 LEDS and exposure time
    # TODO: Example see Figure 22 in NEXTA paper. LED_blink_time/number_rows_lit


    last_y = None
    row_deltas = []
    first_err_row = None
    last_err_row = None
    last_v = None

    # Generate some stats
    for y in timed_rows.keys():
        # To try to get rolling shutter time, only use values with 10^-4 or better resolution
        # maybe this could be an argument, in case using a global shutter camera with longer exposure
        if timed_rows[y]['err'] <= -4:
            v = float(timed_rows[y]['value'])
            orig_v = v
            if increasing and v < 0.2 and last_v is not None and last_v > 9.8:
                v += 10.0
            elif not increasing and v > 9.8 and last_v is not None and last_v < 0.2:
                v -= 10.0
            if last_y is not None:
                tdelta = (v - last_v) / (y - last_y)
                row_deltas.append(tdelta)
            else:
                first_err_row = {'row': y, 'value': float(timed_rows[y]['value'])}
            last_err_row = {'row': y, 'value': float(timed_rows[y]['value'])}
            last_y = y
            last_v = orig_v
    if verbose >= 1:
        print(row_deltas)
    mean_rowtime = np.array(row_deltas).mean()
    if verbose >= 1:
        print('Mean rowtime dt:', mean_rowtime)
    first_last_led_rowtime = (first_err_row['value'] - last_err_row['value']) / (
            first_err_row['row'] - last_err_row['row'])
    if verbose >= 1:
        print('first - last / ydelta:', first_last_led_rowtime)
    first_pixel_time = last_v - mean_rowtime * last_y
    last_pixel_time = last_v + mean_rowtime * (rows - last_y)
    if first_pixel_time < 0 or fits_header_nextatime >= 8 and first_pixel_time <= 2:
        first_pixel_time = 10 + first_pixel_time
    if last_pixel_time < 0 or fits_header_nextatime >= 8 and last_pixel_time <= 2:
        last_pixel_time = 10 + last_pixel_time
    full_readout_time = last_pixel_time - first_pixel_time
    if verbose >= 1:
        print('First pixel Time: ', first_pixel_time, 'Last pixel time: ', last_pixel_time, 'Full readout time:',
              full_readout_time)
    fits_delta = first_pixel_time - fits_header_nextatime
    if verbose >= 1:
        print('Fits DATE-OBS adjustment needed: ', fits_delta)

    return {'mean_row_time': mean_rowtime, 'first_last_per_row_time': first_last_led_rowtime,
            'calc_first_pixel': first_pixel_time, 'fits_time': fits_header_nextatime, 'fits_delta': fits_delta,
            'calc_last_pixel': last_pixel_time, 'full_readout_time': full_readout_time}


def main(roi_json_path, fits_path, output_fn, dscale=-1, verbose=0):
    with open(roi_json_path) as f:
        rois = json.load(f)

    # TODO: Support multichannel/bayer images
    fitsimg = fits.open(fits_path)
    img = fitsimg[0].data
    stretched_image = np.uint8(Stretch().stretch(img) * 255)
    if dscale > 0:
        dscale = dscale
    else:
        dscale = 1000 / max(stretched_image.shape)
    date_obs = fitsimg[0].header['DATE-OBS']

    if verbose >= 2:
        scale_imshow('debug', stretched_image, dscale)
        cv2.waitKey(10000)
    if verbose >= 1:
        print('stretched_image', stretched_image.shape, stretched_image.dtype)

    led_on_thresh = get_led_on_threshold(rois, stretched_image, dscale, verbose)

    y_min, y_max = get_y_roi_range(rois, verbose)

    timed_rows = get_timing_led_rows(y_min, y_max, stretched_image, led_on_thresh, rois, verbose)

    # Decode each row on/off LEDs
    decode_failed_rows = 0
    for y in list(timed_rows.keys()):
        timed_rows[y] = decode_nexta_time(timed_rows[y])
        if timed_rows[y] is None:
            decode_failed_rows += 1
            del timed_rows[y]
    if verbose >= 1:
        print('Rows failed to decode: ', decode_failed_rows)

    # NEXTA time only has goes 0-10s, to compare we do same with date-obs
    fits_seconds = date_obs[date_obs.rfind(':') + 1:]
    fits_header_nextatime = float(fits_seconds) % 10
    if verbose >= 1:
        print('Fits Seconds: ', date_obs, fits_seconds, float(fits_seconds) % 10)
        print('Found ', len(timed_rows.keys()), 'Timing Rows')


    timed_rows, increasing = filter_outliers(timed_rows, fits_header_nextatime, verbose)

    # Calculate rolling shutter time
    timing_stats = calculate_stats(timed_rows, increasing, stretched_image.shape[0], fits_header_nextatime, verbose)
    with open(output_fn, 'w') as f:
        save_data = {'timed_rows': timed_rows}
        save_data.update(timing_stats)
        json.dump(save_data, f, indent=4)


def main_cli():
    import argparse
    parser = argparse.ArgumentParser(
        prog='LED Selector',
        description='Selects LED areas in timing board')
    parser.add_argument('--image', '-i', required=True, type=str,
                        help='FiTS image to read')
    parser.add_argument('--output', '-o', required=True, type=str, help='Output of time data')
    parser.add_argument('--scale', '-s', type=float, required=False, default=-1,
                        help='How much to scale manual area selection image or debug images, defaults to an calculated reasonable value to fit on screen')
    parser.add_argument('--registration', '-r', required=True, type=str,
                        help="Path to registration file created by led_selector")
    parser.add_argument('--verbose', '-v', action='count', default=0,
                        help='How much debug info, -v for text, -vv for graphical debug info')
    args = parser.parse_args()

    main(args.registration, args.image, args.output, args.scale, verbose=args.verbose)


if __name__ == '__main__':
    main_cli()
