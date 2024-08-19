#!/usr/bin/env python
#
#    AStream: Python based DASH player emulator to evaluate the rate adaptation algorithms
#             for DASH.
#    Copyright (C) 2015, Parikshit Juluri
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

from time import strftime
import os
# The configuration file for the AStream module
# create logger
LOG_NAME = 'AStream_log'
LOG_LEVEL = None

# Set '-' to print to screen
LOG_FOLDER = "ASTREAM_LOGS/"
# SUBFOLDERS = ["BASIC", "BASIC-MCOM", "BOLA", "BOLA-MCOM", "NETFLIX", "NETFLIX-MCOM", "SARA", "SARA-MCOM"]
if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)
# for sf in SUBFOLDERS:
#     if not os.path.exists(os.path.join(LOG_FOLDER, sf)):
#         os.makedirs(os.path.join(LOG_FOLDER, sf))

LOG_FILENAME = 'DASH_RUNTIME_LOG'
# Logs related to the statistics for the video
# PLAYBACK_LOG_FILENAME = os.path.join(LOG_FOLDER, strftime('DASH_PLAYBACK_LOG_%Y-%m-%d.%H_%M_%S.csv'))
# Buffer logs created by dash_buffer.py
BUFFER_LOG_FILENAME = strftime('DASH_BUFFER_LOG_%Y-%m-%d.%H_%M_%S.csv')
LOG_FILE_HANDLE = None
# To be set by configure_log_file.py
LOG = None
# JSON Filename
JSON_LOG = strftime('ASTREAM_%Y-%m-%d.%H_%M_%S.json')
JSON_QOE_INPUT_LOG = strftime('QOE_INPUT_%Y-%m-%d.%H_%M_%S.json')
JSON_QOE_OUTPUT_LOG = strftime('QOE_OUTPUT_%Y-%m-%d.%H_%M_%S.json')
JSON_HANDLE = dict()
JSON_HANDLE['playback_info'] = {'start_time': None,
                                'end_time': None,
                                'initial_buffering_duration': None,
                                'interruptions': {'count': 0, 'events': list(), 'total_duration': 0},
                                'up_shifts': 0,
                                'down_shifts': 0
                                }
# Constants for the BASIC-2 adaptation scheme
BASIC_THRESHOLD = 10
BASIC_UPPER_THRESHOLD = 1.2
# Number of segments for moving average
BASIC_DELTA_COUNT = 5

# ---------------------------------------------------
# SARA (Segment Aware Rate Adaptation)
# ---------------------------------------------------
# Number of segments for moving weighted average
SARA_SAMPLE_COUNT = 5
# Constants for the Buffer in the Weighted adaptation scheme (in segments)
INITIAL_BUFFERING_COUNT = 1
RE_BUFFERING_COUNT = 1
ALPHA_BUFFER_COUNT = 2  # 20s: 2, 40s: 5
BETA_BUFFER_COUNT = 4  # 20s: 4, 40s: 10

# ---------------------------------------------------
# Netflix (Buffer-based) ADAPTATION
# ---------------------------------------------------
# Constants for the Netflix Buffering scheme adaptation/netflix_buffer.py
# Constants is terms of buffer occupancy PERCENTAGE(%)
NETFLIX_RESERVOIR = 0.1
NETFLIX_CUSHION = 0.9
# Buffer Size in seconds
NETFLIX_BUFFER_SIZE_SECONDS = 20  # 120
# Buffer Size in Number of segments -> BUFFER_SIZE_SECONDS/SEG_LENGTH -> Adjust in dash_client
NETFLIX_BUFFER_SIZE = NETFLIX_BUFFER_SIZE_SECONDS / 4  # Use 4 as default segment length
NETFLIX_INITIAL_BUFFER = 2
NETFLIX_INITIAL_FACTOR = 0.875

# ---------------------------------------------------
# BOLA ADAPTATION
# ---------------------------------------------------
# Constants for the BOLA scheme adaptation/bola_dash.py (Buffer related constants are all in seconds)
BOLA_STATE_ONE_BITRATE = 0
BOLA_STATE_STARTUP = 1
BOLA_STATE_STEADY = 2
MINIMUM_BUFFER_S = 8  # BOLA should never add artificial delays if buffer is less than MINIMUM_BUFFER_S.
STABLE_BUFFER_TIME = 10 # 20s: 10 # 40s: 20

MINIMUM_BUFFER_PER_BITRATE_LEVEL_S = 2  # E.g. if there are 5 bitrates, BOLA switches to top bitrate at buffer = MINIMUM_BUFFER_S + 5 * MINIMUM_BUFFER_PER_BITRATE_LEVEL_S = X [s].
# If Schedule Controller does not allow buffer to reach that level, it can be achieved through the placeholder buffer level.

PLACEHOLDER_BUFFER_DECAY = 0.99  # Make sure placeholder buffer does not stick around too long.

# Set the size of the buffer in terms of segments. Set to unlimited if 0 or None
MAX_BUFFER_SIZE = None

# For ping.py
PING_PACKETS = 10
ping_option_nb_pkts = PING_PACKETS
rtt_match = None
rtt_pattern = None
index_rtt_min = None
index_rtt_avg = None
index_rtt_max = None
RTT = False
