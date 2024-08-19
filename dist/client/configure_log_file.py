import logging
import config_dash
import sys
from time import strftime
import io
import json
import os
#from p1203Pv_extended.p1203Pv_extended import P1203Pv_codec_extended
#from itu_p1203 import P1203Standalone

# Dictionary for gathering data from AStream - JSON logs
SEGMENT_NAME = 0
BITRATE = 1
CODEC = 2
VMAF = 3
SEGMENT_SIZE = 4
SEGMENT_DOWNLOAD_TIME = 5
RESOLUTION = 6

DEVICE = "pc"
VIEWING_DISTANCE = "150cm"
DISPLAY_SIZE = "3840x2160"


def configure_log_file(playback_type="", log_file=config_dash.LOG_FILENAME, multi_codec=False):
    """ Module to configure the log file and the log parameters.
    Logs are streamed to the log file as well as the screen.
    Log Levels: CRITICAL:50, ERROR:40, WARNING:30, INFO:20, DEBUG:10, NOTSET	0
    """
    # Change path for all logging files
    # if playback_type == "all":
    #     log_file = os.path.join(config_dash.LOG_FOLDER, log_file)
    #     config_dash.BUFFER_LOG_FILENAME = os.path.join(config_dash.LOG_FOLDER, config_dash.BUFFER_LOG_FILENAME)
    #     config_dash.JSON_LOG = os.path.join(config_dash.LOG_FOLDER, config_dash.JSON_LOG)
    #     config_dash.JSON_QOE_INPUT_LOG = os.path.join(config_dash.LOG_FOLDER, config_dash.JSON_QOE_INPUT_LOG)
    #     config_dash.JSON_QOE_OUTPUT_LOG = os.path.join(config_dash.LOG_FOLDER, config_dash.JSON_QOE_OUTPUT_LOG)
    # else:
    #     if multi_codec:
    #         playback_type += "-mcom"
    #     log_file = os.path.join(config_dash.LOG_FOLDER, playback_type.upper(), log_file)
    #     config_dash.BUFFER_LOG_FILENAME = os.path.join(config_dash.LOG_FOLDER, playback_type.upper(), config_dash.BUFFER_LOG_FILENAME)
    #     config_dash.JSON_LOG = os.path.join(config_dash.LOG_FOLDER, playback_type.upper(), config_dash.JSON_LOG)
    #     config_dash.JSON_QOE_INPUT_LOG = os.path.join(config_dash.LOG_FOLDER, playback_type.upper(), config_dash.JSON_QOE_INPUT_LOG)
    #     config_dash.JSON_QOE_OUTPUT_LOG = os.path.join(config_dash.LOG_FOLDER, playback_type.upper(), config_dash.JSON_QOE_OUTPUT_LOG)
    log_file = os.path.join(config_dash.LOG_FOLDER, log_file)
    config_dash.BUFFER_LOG_FILENAME = os.path.join(config_dash.LOG_FOLDER, config_dash.BUFFER_LOG_FILENAME)
    config_dash.JSON_LOG = os.path.join(config_dash.LOG_FOLDER, config_dash.JSON_LOG)
    config_dash.JSON_QOE_INPUT_LOG = os.path.join(config_dash.LOG_FOLDER, config_dash.JSON_QOE_INPUT_LOG)
    config_dash.JSON_QOE_OUTPUT_LOG = os.path.join(config_dash.LOG_FOLDER, config_dash.JSON_QOE_OUTPUT_LOG)
    # print(log_file)
    # print(config_dash.BUFFER_LOG_FILENAME)
    # print(config_dash.JSON_LOG)
    # print(config_dash.JSON_QOE_INPUT_LOG)
    # print(config_dash.JSON_QOE_OUTPUT_LOG)
    # Edit the LOG_FILENAME
    config_dash.LOG = logging.getLogger(config_dash.LOG_NAME)
    config_dash.LOG_LEVEL = logging.INFO
    config_dash.LOG.setLevel(config_dash.LOG_LEVEL)
    log_formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s')
    # Add the handler to print to the screen
    handler1 = logging.StreamHandler(sys.stdout)
    handler1.setFormatter(log_formatter)
    config_dash.LOG.addHandler(handler1)
    # Add the handler to for the file if present
    if log_file:
        log_filename = "_".join((log_file, playback_type, strftime('%Y-%m-%d.%H_%M_%S.log')))
        print("Configuring log file: {}".format(log_filename))
        handler2 = logging.FileHandler(filename=log_filename)
        handler2.setFormatter(log_formatter)
        config_dash.LOG.addHandler(handler2)
        print("Started logging in the log file:{}".format(log_file))


def write_json(json_data=config_dash.JSON_HANDLE, json_file=config_dash.JSON_LOG):
    """
    :param json_data: dict
    :param json_file: json file
    :return: None
        Using utf-8 to reduce size of the file
    """
    # print(json_file)
    with open(json_file, 'w') as json_file_handle:
        json_file_handle.write(json.dumps(json_data))


def write_input_qoe(segment_length, json_data=config_dash.JSON_HANDLE, json_file=config_dash.JSON_QOE_INPUT_LOG):
    # Create and populate ITU-T P.1203-compliant JSON input file
    jsonString = "{\"I11\":{\"segments\":[],\"streamId\":42},\"I13\":{\"segments\":["
    start = 0
    for segment_info in json_data["segment_info"]:
        if segment_info[SEGMENT_NAME][-4:] == ".mp4":  # initialization segment
            continue
        c = segment_info[CODEC].lower()
        if "avc" in c:  # Name for AVC should be H264. "AVC" not supported by ITU-T P.1203 model
            c = "h264"
        elif "hev1" in c:
            c = "hevc"
        elif "av" in c or "vp09" in c:  # AV1 not supported by ITU-T P.1203 model
            c = "vp9"
        jsonString += "{{\"bitrate\":{:n},\"codec\":\"{:s}\",\"duration\":{:n},\"fps\":{:n},\"resolution\":\"{:s}\",\"start\":{:n}}},".format(
            segment_info[BITRATE] / 1000, c, segment_length, 24, segment_info[RESOLUTION], start)
        start += segment_length
    jsonString = jsonString[:-1]  # Remove the exceeding comma
    jsonString += "],\"streamId\":42},\"I23\":{\"stalling\":["
    # start_time = json_data["playback_info"]["start_time"]
    start_up = json_data["playback_info"]["initial_buffering_duration"]
    jsonString += "[{:.3f},{:.3f}],".format(0, start_up)  # Initial buffering time
    for stall_pair in json_data["playback_info"]["interruptions"]["events"]:
        time = stall_pair[0]
        duration = stall_pair[1] - stall_pair[0]
        jsonString += "[{:.3f},{:.3f}],".format(time, duration)
    jsonString = jsonString[:-1]  # Remove the exceeding comma
    jsonString += "],\"streamId\": 42}},\"IGen\":{{\"device\":\"{:s}\",\"displaySize\":\"{:s}\",\"viewingDistance\":\"{:s}\"}}}}".format(
        DEVICE, DISPLAY_SIZE, VIEWING_DISTANCE)
    # Using a JSON string
    with open(json_file, 'w') as outfile:
        outfile.write(jsonString)


#def write_output_qoe(json_in_file=config_dash.JSON_QOE_INPUT_LOG, json_out_file=config_dash.JSON_QOE_OUTPUT_LOG):
    # print(json_in_file)
    # print(json_out_file)
    #with open(json_in_file, "r") as in_fp:
        #results = P1203Standalone(json.load(in_fp), Pv=P1203Pv_codec_extended).calculate_complete()
        #with open(json_out_file, 'w') as outfile:
            #json.dump(results, outfile, indent=4)
