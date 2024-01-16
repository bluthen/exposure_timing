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

import argparse
import cv2
import sys
import numpy as np

ARUCO_DICT = cv2.aruco.DICT_4X4_50

def detect(image):
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    aruco_params = cv2.aruco.DetectorParameters()
    aruco_params.adaptiveThreshWinSizeStep=5
    aruco_params.adaptiveThreshWinSizeMax=100
    print(aruco_params)
    detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    corners, ids, rejected = detector.detectMarkers(image)
    # print(rejected)
    if ids is not None:
        ids = ids.flatten()
        # print(corners)
        # print(ids)
        ret = {}
        for (corner, id) in zip(corners, ids):
            # print('id', id)
            # print('corner', corner)
            ret[id] = {
                'corners': corner[0],
                'center': [(corner[0][0][0]+corner[0][2][0])/2., (corner[0][0][1]+corner[0][2][1])/2.]
           }
    return ret, sorted(ids), [corners, ids]
