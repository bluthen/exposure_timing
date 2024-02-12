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

import glob
import json
import os
import traceback

import numpy as np

import read_time


def main_cli():
    #fits_glob_pattern = './example_files/aLight*.fits'
    fits_glob_pattern = 'asi1600m-3/Light/aLight*.fits'
    fits_files = glob.glob(fits_glob_pattern)
    roi_file = 'registration.etreg'
    i = 0
    for fit_fn in fits_files:
        print(str(i+1) + '/' + str(len(fits_files)), fit_fn, end='\r')
        try:
            read_time.main(roi_file, fit_fn, fit_fn + '.ettime')
        except Exception as e:
            print()
            traceback.print_exception(e)
        i += 1
    print()
    # Lets load up outputs and do some averaging.
    json_files = glob.glob(os.path.splitext(fits_glob_pattern)[0] + '.ettime')
    rolling_shutter_row_time = []
    fits_delta = []
    full_readout_time = []
    for json_fn in json_files:
        with open(json_fn) as f:
            fjson = json.load(f)
            rolling_shutter_row_time.append(fjson['rolling_shutter_row_time'])
            fits_delta.append(fjson['fits_delta'])
            full_readout_time.append(fjson['full_readout_time'])
    print(json.dumps(
        {'rolling_shutter_row_time': np.array(rolling_shutter_row_time).mean(),
         'fits_delta': {'min': np.array(fits_delta).min(), 'max': np.array(fits_delta).max(),
                        'mean': np.array(fits_delta).mean(), 'stdev': np.array(fits_delta).std()},
         'full_readout_time': np.array(full_readout_time).mean()}, indent=4))


if __name__ == '__main__':
    main_cli()
