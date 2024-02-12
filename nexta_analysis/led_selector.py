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


import json
import math
import traceback

import cv2
import numpy as np
from auto_stretch.stretch import Stretch

import aruco_detect
import debug_show
import read_time

# Each board with different spacing should have different ARUCO markers ids to identify them automatically.
# IDs_ARRAY: {version:
# TODO: Lets clean this up and keep only what we use, we don't need all this info for a board.
BOARDS = {
    '[0, 1, 2]': {
        'version': 'v1.x.x',
        'distances': {'0-1': 61.530, '1-2': 32.659, '0-2': 33.244},
        'angles': {'0-2': 0.35953782591, '1-2': 2.76634686441, '0-1': 0.0},  # rad
        'leds': {
            'size': 10,
            'ledsize': [1.78, 5.08],
            'width': 25.27,
            'sep': 2.54,
            '0-1': 4.0,  # 4.952
            '0-11': 31.564,
            'v': 5.30  # 5.39
        }
    },
    '[0, 1, 3, 4]': {
        'version': 'v2.x.x',
        'distances': {'0-1': 61.680},
        'leds': {
            'ledsize': [1.78, 5.08],
            '0-1': 4.0,  # 4.952
            'v': 5.30  # 5.39
        }
    }
}


def shrink_line_remove_mark(line, px_per_mm, marker_mm):
    """
    Moves the sides of the rectangle inward so it only is led bars and not markers.
    :param line:
    :param px_per_mm:
    :param marker_mm:
    :return:
    """
    v = [line[1][0] - line[0][0], line[1][1] - line[0][1]]
    vlen = math.sqrt(v[0] * v[0] + v[1] * v[1])
    v1 = [v[0] / vlen, v[1] / vlen]
    u1 = v1
    p1 = [line[0][0] + u1[0] * (px_per_mm * marker_mm), line[0][1] + u1[1] * (px_per_mm * marker_mm)]

    p3 = [line[1][0] - u1[0] * (px_per_mm * marker_mm), line[1][1] - u1[1] * (px_per_mm * marker_mm)]
    # p4 = [line[1][0] + u1[0] * l2 / 2, line[1][1] + u1[1] * l2 / 2]
    points = np.int32([p1, p3])
    return points


def expand_rect_from_line(line, l2):
    """
    Give a line this give a rectangle by moving it out on either side by l2/2
    :param line:
    :param l2:
    :return: Points of the rectangle.
    """
    mline = [(line[0][0] + line[1][0]) / 2, (line[0][1] + line[1][1]) / 2]

    # We expand the line between the Aruco points
    v = [line[1][0] - line[0][0], line[1][1] - line[0][1]]
    vlen = math.sqrt(v[0] * v[0] + v[1] * v[1])
    v1 = [v[0] / vlen, v[1] / vlen]
    u1 = [-v1[1], v1[0]]
    p1 = [line[0][0] + u1[0] * l2 / 2, line[0][1] + u1[1] * l2 / 2]
    p2 = [line[0][0] - u1[0] * l2 / 2, line[0][1] - u1[1] * l2 / 2]

    p3 = [line[1][0] - u1[0] * l2 / 2, line[1][1] - u1[1] * l2 / 2]
    p4 = [line[1][0] + u1[0] * l2 / 2, line[1][1] + u1[1] * l2 / 2]
    points = np.int32([p1, p2, p3, p4])

    # rect = cv2.minAreaRect(points)
    # box = cv2.boxPoints(rect)
    # box = np.int32(box)

    return points


def get_aruco_points(img, dscale, verbose=0):
    """
    Find the ids and center points for our aruco markers.
    :param img:
    :param dscale:
    :param verbose:
    :return:
    """
    # Aruco Detect expects black markers, but we put white ones in the board so we invert.
    iimg = 255 - np.uint8(img)
    # Dust, hair, slight shadows can cause an issue, so we blur to try to work around that.
    iimg = cv2.GaussianBlur(iimg, (15, 15), 0)
    arucos, ids, debug_info = aruco_detect.detect(iimg)
    if verbose >= 2:
        debug_img = cv2.cvtColor(np.float32(iimg), cv2.COLOR_GRAY2BGR)
        for k in arucos.keys():
            mark = arucos[k]
            cv2.circle(debug_img, np.int32(np.array(mark['center'])), int(5 / dscale), (0, 0, 255), -1)
        cv2.aruco.drawDetectedMarkers(debug_img, debug_info[0], debug_info[1])
        debug_show.show('debug', debug_img)
        debug_show.wait(10000)
    if str(ids) not in BOARDS:
        raise Exception('Unable to find board with detected markers: ' + str(ids))
    return arucos, ids


def get_led_roi(arucos, ids, img, dscale, verbose=0):
    """
    Using aruco markers as guide it finds the region of interest of our LED bars.
    :param arucos:
    :param ids:
    :param img:
    :param dscale:
    :param verbose:
    :return:
    """
    # Line distance between first and second points (points on either side of LED array
    d0_1 = np.linalg.norm(np.array(arucos[ids[0]]['center']) - np.array(arucos[ids[1]]['center']))
    # From the distance of the markers, how many pixels per mm
    roi_px_per_mm = d0_1 / BOARDS[str(ids)]['distances']['0-1']
    roi_line = [arucos[ids[0]]['center'], arucos[ids[1]]['center']]
    roi_line = shrink_line_remove_mark(roi_line, roi_px_per_mm, BOARDS[str(ids)]['leds']['0-1'])
    roi_height = BOARDS[str(ids)]['leds']['v'] * roi_px_per_mm
    rect = expand_rect_from_line(roi_line, roi_height * 2)
    roi_mask = read_time.get_poly_mask(img, rect)

    if verbose >= 1:
        print(rect)
    if verbose >= 2:
        debug_img = cv2.cvtColor(np.float32(img), cv2.COLOR_GRAY2BGR)
        cv2.polylines(debug_img, [np.array(rect).reshape((-1, 1, 2))], True, (255, 0, 0), int(2 / dscale))
        debug_show.show('debug', debug_img)
        debug_show.wait(10000)

    return roi_mask, roi_line, roi_px_per_mm, rect


def get_roi_image(img, roi_rect, roi_mask, verbose=0):
    """
    Gives image with only LED bars non-zero
    :param img:
    :param roi_rect:
    :param roi_mask:
    :param verbose:
    :return:
    """
    # ROI Stats
    led_roi_values = read_time.get_poly_values(img, roi_rect)
    led_roi_mean = led_roi_values.mean()
    led_roi_std = led_roi_values.std()

    img_led = img.copy()
    # roi_image is only led bargraph coponent, everything else is black
    roi_image = cv2.bitwise_and(img_led, img_led, mask=np.uint8(roi_mask) * 255)
    if verbose >= 1:
        print('stat:', led_roi_mean, led_roi_std)
    return roi_image, led_roi_mean


def get_contours(roi_image, roi_mean, img, dscale, verbose=0):
    """
    Find LED contours from a image with LED bars having value.
    :param roi_image: Image with just the LED bars as non-zero
    :param roi_mean: Mean of the LED bar area
    :param img: Original area
    :param dscale: debug scaling value
    :param verbose: how much debug output
    :return: LED contours
    """
    # Find Contours
    # Since ROI is LEDs and LED bar border, the mean should be a good way to serperate them.
    test_edge_thresh = cv2.threshold(np.uint8(roi_image), roi_mean, 255, cv2.THRESH_BINARY)[1]
    if verbose >= 2:
        debug_show.show('debug', test_edge_thresh)
        debug_show.wait(10000)
    contours, hierarchy = cv2.findContours(test_edge_thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if verbose >= 2:
        debug_img = cv2.cvtColor(np.float32(img), cv2.COLOR_GRAY2BGR)

        cv2.drawContours(debug_img, contours, -1, (0, 255, 0), int(3 / dscale))
        debug_show.show('debug', debug_img)
        debug_show.wait(10000)
    return contours


def find_ordered_LED_polypoints(img, dscale, verbose=0):
    """
    Automated method to try to find LED polygons.
    :param img:
    :param dscale:
    :param verbose:
    :return:
    """
    debug_img = cv2.cvtColor(np.float32(img), cv2.COLOR_GRAY2BGR)

    # First find Aruco points
    arucos, ids = get_aruco_points(img, dscale, verbose)

    roi_mask, roi_line, roi_px_per_mm, roi_rect = get_led_roi(arucos, ids, img, dscale, verbose)

    roi_image, roi_mean = get_roi_image(img, roi_rect, roi_mask, verbose)
    contours = get_contours(roi_image, roi_mean, img, dscale, verbose)

    # Filter contours to find our LEDs
    # Only care about the contours that are LEDs
    led_area = roi_px_per_mm * roi_px_per_mm * BOARDS[str(ids)]['leds']['ledsize'][0] * \
               BOARDS[str(ids)]['leds']['ledsize'][1]
    ourleds = []
    for contour in contours:
        # It is our LED if it has close to correct area, and center of mass is nearest our roi_line
        M = cv2.moments(contour)
        contour_area = M['m00']
        # If area is not zero and within +- 25% of expected led_area, could be our LED
        if led_area * 1.25 > contour_area > led_area * 0.75:
            centroid = np.array([M['m10'] / contour_area, M['m01'] / contour_area])
            roi_line = np.array(roi_line)
            # Calculate distance from contour centroid and our ROI line (middle of LED bar graph component)
            linedistance = np.abs(np.cross(roi_line[1] - roi_line[0], roi_line[0] - centroid)) / np.linalg.norm(
                roi_line[1] - roi_line[0])
            # Distance from aruco first point in roi_line indicates order
            aruco0_distance = np.linalg.norm(centroid - roi_line[0])
            ourled = {'contour': contour, 'area': contour_area, 'centroid_distance': linedistance, 'centroid': centroid,
                      'aruco0_distance': aruco0_distance}
            ourleds.append(ourled)
    # Only loook at the first 20 closest to the line.
    ourleds = sorted(ourleds, key=lambda x: x['centroid_distance'])
    if len(ourleds) > 20:
        ourleds = ourleds[0:20]
    # Sort by how close to aruco0, closest to arcuo0 is seconds, farthest is 10^-4s
    ourleds = sorted(ourleds, key=lambda x: x['aruco0_distance'])
    place = 0
    subplace = 0
    for ourled in ourleds:
        # lets simplify our contour to a low res polly, it doesn't need to be super complicated, LEDs are rectangular
        poly_point_count = 0
        lfactor = 0.005
        simplify_count = 0
        while poly_point_count <= 3:
            epsilon = lfactor * cv2.arcLength(ourled['contour'], True)
            poly = cv2.approxPolyDP(ourled['contour'], epsilon, True)
            poly_point_count = max(poly.shape)
            # print(epsilon, poly_point_count)
            lfactor = lfactor * 2
        # The points of the poly is what we really want at the end of all this.
        ourled['poly'] = poly
        points = []
        for p in poly:
            points.append(p[0].tolist())
        ourled['points'] = points
        if verbose >= 2:
            cv2.circle(debug_img, np.int32(ourled['centroid']), int(5 / dscale), (255, 0, 255), -1)
            cv2.polylines(debug_img, [poly.reshape((-1, 1, 2))], True, (255, 0, 255), int(2 / dscale + 0.5))
            text = ('-' if place > 0 else '') + str(place) + chr(97 + subplace)
            uzpoints = list(zip(*points))
            pos = [min(uzpoints[0]), min(uzpoints[1])]
            cv2.putText(debug_img, text, pos, cv2.FONT_HERSHEY_COMPLEX, .4 / dscale, (255, 255, 0),
                        int(1 / dscale + 0.5), cv2.LINE_AA)
        subplace += 1
        if subplace == 4:
            place += 1
            subplace = 0

    if verbose >= 2:
        debug_show.show('debug', debug_img)
        debug_show.wait(10000)
    # Make our array of ordered poly points.
    ret = [ourled['points'] for ourled in ourleds]
    return ret


def draw_ordered_led_polys(img, points, dscale):
    """
    Draws outline of led polygons, and some font about what value it represents.
    :param img:
    :param points:
    :param dscale:
    :return:
    """
    debug_img = cv2.cvtColor(np.float32(img), cv2.COLOR_GRAY2BGR)

    place = 0
    subplace = 0
    for poly in points:
        cv2.polylines(debug_img, [np.array(poly).reshape((-1, 1, 2))], True, (255, 0, 255), int(2 / dscale))
        text = ('-' if place > 0 else '') + str(place) + chr(97 + subplace)
        uzpoints = list(zip(*poly))
        pos = [min(uzpoints[0]), min(uzpoints[1])]
        cv2.putText(debug_img, text, pos, cv2.FONT_HERSHEY_COMPLEX, .4 / dscale, (255, 255, 0), int(1 / dscale),
                    cv2.LINE_AA)
        subplace += 1
        if subplace == 4:
            place += 1
            subplace = 0
    return debug_img


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog='LED Selector',
        description='Selects LED areas in timing board')
    parser.add_argument('--reference_image', '-i', required=True, type=str,
                        help='Reference image used to get placement of LED Array')
    parser.add_argument('--output', '-o', required=True, type=str, help='Output of Registration data')
    parser.add_argument('--scale', '-s', type=float, required=False, default=-1,
                        help='How much to scale manual area selection image or debug images, defaults to an calculated reasonable value to fit on screen')
    parser.add_argument('--verbose', '-v', action='count', default=0,
                        help='How much debug info, -v for text, -vv for graphical debug info')
    args = parser.parse_args()
    imgname = args.reference_image
    # img = cv2.imread(sys.argv[1])
    img = read_time.open_fits(imgname)[0]
    stretched_img = np.uint8(Stretch().stretch(img) * 255)
    if args.scale > 0:
        scale = args.scale
    else:
        scale = 1000 / max(img.shape)
    led_poly_points = []
    try:
        led_poly_points = find_ordered_LED_polypoints(stretched_img, scale, args.verbose)
    except Exception as e:
        if args.verbose >= 1:
            traceback.print_exception(e)
    if args.verbose >= 1:
        print('Number of polys:', len(led_poly_points))
    if len(led_poly_points) != 20:
        raise (Exception('Not able to auto detect LED bar graph, using GUI to manually make registration file.'))
    with open(args.output, 'w') as f:
        json.dump(led_poly_points, f)
    # Lets show the final result.
    pimg = draw_ordered_led_polys(stretched_img, led_poly_points, scale)
    debug_show.show('complete', pimg)
    debug_show.wait(20000)
    print('Done.')


if __name__ == '__main__':
    main()
