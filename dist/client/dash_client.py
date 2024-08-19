#!/usr/local/bin/python
"""
Author:            Parikshit Juluri
Contact:           pjuluri@umkc.edu
Testing:
    import dash_client
    mpd_file = <MPD_FILE>
    dash_client.playback_duration(mpd_file, 'http://198.248.242.16:8005/')

    From commandline:
    python3 dash_client.py -m "http://198.248.242.16:8006/media/mpd/x4ukwHdACDw.mpd" -p "all"
    python3 dash_client.py -m "http://127.0.0.1:8000/media/mpd/x4ukwHdACDw.mpd" -p "basic"

"""
from __future__ import division
import read_mpd
try:
    import urllib.parse as urlparse  # working for Python3
except ImportError:
    import urlparse
try:
    import urllib.request as urllib2  # working for Python3
except ImportError:
    import urllib2
import random
import os
import sys
import errno
import timeit
try:
    import http.client as httplib  # working for Python3
except ImportError:
    import httplib
from string import ascii_letters, digits
from argparse import ArgumentParser
from multiprocessing import Process, Queue
from collections import defaultdict
from adaptation import basic_dash, basic_dash2, bola_paper, weighted_dash, netflix_dash, mcom_dash, medusa
from adaptation.base_adaptation import WeightedMean
import config_dash
import dash_buffer
from configure_log_file import configure_log_file, write_json, write_input_qoe#, write_output_qoe
import time
from read_mpd import DashPlayback


# Constants
DEFAULT_PLAYBACK = 'BASIC'
DOWNLOAD_CHUNK = 1024


def get_mpd(url):
    """ Module to download the MPD from the URL and save it to file"""
    print(url)
    try:
        connection = urllib2.urlopen(url, timeout=10)
    except urllib2.HTTPError as error:
        config_dash.LOG.error("Unable to download MPD file HTTP Error: %s" % error.code)
        return None
    except urllib2.URLError:
        error_message = "URLError. Unable to reach Server.Check if Server active"
        config_dash.LOG.error(error_message)
        print(error_message)
        return None
    except (IOError, httplib.HTTPException) as e:
        message = "Unable to , file_identifierdownload MPD file HTTP Error."
        config_dash.LOG.error(message)
        return None
    
    mpd_data = connection.read()
    connection.close()
    mpd_file = url.split('/')[-1]
    mpd_file_handle = open(mpd_file, 'wb')
    mpd_file_handle.write(mpd_data)
    mpd_file_handle.close()
    config_dash.LOG.info("Downloaded the MPD file {}".format(mpd_file))
    return mpd_file


def get_bandwidth(data, duration):
    """ Module to determine the bandwidth for a segment
    download"""
    return data * 8/duration


def get_domain_name(url):
    """ Module to obtain the domain name from the URL
        From : http://stackoverflow.com/questions/9626535/get-domain-name-from-url
    """
    # parsed_uri = urlparse.urlparse(url)
    # domain = '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)
    domain = '/'.join(url.split('/')[:-1]) + '/'
    return domain


def id_generator(id_size=6):
    """ Module to create a random string with uppercase 
        and digits.
    """
    return 'TEMP_' + ''.join(random.choice(ascii_letters+digits) for _ in range(id_size))


def download_segment(segment_url, dash_folder):
    """ Module to download the segment """
    try:
        connection = urllib2.urlopen(segment_url)
    except urllib2.HTTPError as error:
        config_dash.LOG.error("Unable to download DASH Segment {} HTTP Error:{} ".format(segment_url, str(error.code)))
        return None
    parsed_uri = urlparse.urlparse(segment_url)
    segment_path = '{uri.path}'.format(uri=parsed_uri)
    while segment_path.startswith('/'):
        segment_path = segment_path[1:]        
    segment_filename = os.path.join(dash_folder, os.path.basename(segment_path))
    make_sure_path_exists(os.path.dirname(segment_filename))
    segment_file_handle = open(segment_filename, 'wb')
    segment_size = 0
    while True:
        segment_data = connection.read(DOWNLOAD_CHUNK)
        segment_size += len(segment_data)
        segment_file_handle.write(segment_data)
        if len(segment_data) < DOWNLOAD_CHUNK:
            break
    connection.close()
    segment_file_handle.close()
    #print "segment size = {}".format(segment_size)
    #print "segment filename = {}".format(segment_filename)
    return segment_size, segment_filename


def get_media_all(domain, media_info, file_identifier, done_queue):
    """ Download the media from the list of URL's in media
    """
    bandwidth, media_dict = media_info
    media = media_dict[bandwidth]
    media_start_time = timeit.default_timer()
    for segment in [media.initialization] + media.url_list:
        start_time = timeit.default_timer()
        segment_url = urlparse.urljoin(domain, segment)
        _, segment_file = download_segment(segment_url, file_identifier)
        elapsed = timeit.default_timer() - start_time
        if segment_file:
            done_queue.put((bandwidth, segment_url, elapsed))
    media_download_time = timeit.default_timer() - media_start_time
    done_queue.put((bandwidth, 'STOP', media_download_time))
    return None


def make_sure_path_exists(path):
    """ Module to make sure the path exists if not create it
    """
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def print_representations(dp_object):
    """ Module to print the representations"""
    print("The DASH media has the following video representations/bitrates")
    for adaptationSet in dp_object.adaptationSets:
        print(adaptationSet.id)
        for bandwidth in adaptationSet.video:
            print(bandwidth)


def start_playback_smart(dp_object, domain, playback_type=None, multi_codec=False, download=False, video_segment_duration=None, segment_limit=None):
    """ Module that downloads the MPD-FIle and download
        all the representations of the Module to download
        the MPEG-DASH media.
        Example: start_playback_smart(dp_object, domain, "SMART", DOWNLOAD, video_segment_duration)

        :param dp_object:       The DASH-playback object
        :param domain:          The domain name of the server (The segment URLS are domain + relative_address)
        :param playback_type:   The type of playback
                                1. 'BASIC' - The basic adapataion scheme
                                2. 'SARA' - Segment Aware Rate Adaptation
                                3. 'NETFLIX' - Buffer based adaptation used by Netflix
        :param download: Set to True if the segments are to be stored locally (Boolean). Default False
        :param video_segment_duration: Playback duratoin of each segment
        :return:
    """
    # Initialize the DASH buffer
    dash_player = dash_buffer.DashPlayer(dp_object.playback_duration, video_segment_duration)
    dash_player.start()
    # A folder to save the segments in
    file_identifier = id_generator()
    config_dash.LOG.info("The segments are stored in %s" % file_identifier)
    dp_list = defaultdict(defaultdict)
    # Creating a Dictionary of all that has the URLs for each segment and different bitrates
    for adaptationSet in dp_object.adaptationSets:
        for bitrate in adaptationSet.video:
            # Getting the URL list for each bitrate
            adaptationSet.video[bitrate] = read_mpd.get_url_list(adaptationSet.video[bitrate], video_segment_duration,
                                                             dp_object.playback_duration, bitrate, adaptationSet.video[bitrate].id)

            if "$Bandwidth$" in adaptationSet.video[bitrate].initialization:
                adaptationSet.video[bitrate].initialization = adaptationSet.video[bitrate].initialization.replace(
                    "$Bandwidth$", str(bitrate))
            if "$RepresentationID$" in adaptationSet.video[bitrate].initialization:
                adaptationSet.video[bitrate].initialization = adaptationSet.video[bitrate].initialization.replace("$RepresentationID$", str(adaptationSet.video[bitrate].id))
            # media_urls = [adaptationSet.video[bitrate].initialization] + adaptationSet.video[bitrate].url_list
            media_urls = [adaptationSet.video[bitrate].initialization] + adaptationSet.video[bitrate].url_list
            #print "media urls"
            #print media_urls
            for segment_count, segment_url in enumerate(media_urls, adaptationSet.video[bitrate].start):
                # segment_duration = adaptationSet.video[bitrate].segment_duration
                #print "segment url"
                #print segment_url
                # print("SegmentCount: {}, SegmentUrl: {}, Bitrate: {}, AdaptationSetId: {}".format(segment_count, segment_url, bitrate, adaptationSet.id))
                if segment_count not in dp_list:
                    dp_list[segment_count] = defaultdict(defaultdict)
                if int(adaptationSet.id) not in dp_list[segment_count]:
                    dp_list[segment_count][int(adaptationSet.id)] = defaultdict(defaultdict)
                if bitrate not in dp_list[segment_count][int(adaptationSet.id)]:
                    dp_list[segment_count][int(adaptationSet.id)][bitrate] = segment_url
    # Select the proper AdaptationSet
    adaptationSetIdx = 4
    mcom_adaptationSetIdx = adaptationSetIdx
    bitrates = list(dp_object.getAdaptationSetFromId(adaptationSetIdx).video.keys())
    bitrates.sort()
    average_dwn_time = 0
    segment_files = []
    # For basic adaptation
    previous_segment_times = []
    recent_download_sizes = []
    weighted_mean_object = None
    current_bitrate = bitrates[0]
    mcom_current_bitrate = bitrates[0]
    previous_bitrate = None
    # Stats
    last_throughput = None
    last_buffer_occupancy = None
    total_downloaded = 0
    # Delay in terms of the number of segments
    delay = 0
    segment_duration = 0
    segment_size = segment_download_time = None
    vmaf = None  # gather VMAF from adaptationSet
    # Netflix Variables
    average_segment_sizes = netflix_rate_map = None
    netflix_state = "INITIAL"
    # Start playback of all the segments
    config_dash.LOG.info("{} available segments starting from index {}".format(len(dp_list), dp_object.getAdaptationSetFromId(adaptationSetIdx).video[current_bitrate].start))
    for segment_number, segment in enumerate(dp_list, dp_object.getAdaptationSetFromId(adaptationSetIdx).video[current_bitrate].start - 1):
        config_dash.LOG.info(" {}: Processing the segment {}".format(playback_type.upper(), segment_number))
        write_json(json_file=config_dash.JSON_LOG)
        if not previous_bitrate:
            previous_bitrate = current_bitrate
        if segment_limit:
            if not dash_player.segment_limit:
                dash_player.segment_limit = int(segment_limit)
            if segment_number > int(segment_limit):
                config_dash.LOG.info("Segment limit reached")
                break
        # print("segment_number ={}".format(segment_number))
        # print("dp_object.adaptationSets[{}].video[bitrate].start={}".format(adaptationSetIdx, dp_object.adaptationSets[adaptationSetIdx].video[bitrate].start))
        if segment_number == dp_object.getAdaptationSetFromId(adaptationSetIdx).video[current_bitrate].start - 1:
            current_bitrate = bitrates[0]
        else:
            if playback_type.upper() == "MEDUSA":
                    mcom_current_bitrate, mcom_adaptationSetIdx, vmaf = medusa.medusa_dash(dp_object, dash_player, last_throughput, segment_number)
                                                                                
                    config_dash.LOG.info("MEDUSA results: Adaptation set id {} -> bitrate = {}".format(mcom_adaptationSetIdx,
                                                                                            mcom_current_bitrate))
            else:
                if multi_codec:
                    if playback_type.upper() == "BASIC":
                        current_bitrate, average_dwn_time = basic_dash2.basic_dash2(segment_number, bitrates, average_dwn_time,
                                                                                    recent_download_sizes,
                                                                                    previous_segment_times, current_bitrate)
                        # Replace result with MCOM plugin result
                        mcom_current_bitrate, mcom_adaptationSetIdx, vmaf = mcom_dash.mcom_dash(dp_object, dash_player, last_throughput,
                                                                                                current_bitrate,
                                                                                                adaptationSetIdx,
                                                                                                segment_number)
                                                                                                
                        config_dash.LOG.info("Basic-DASH: Selected {} for the segment {}".format(current_bitrate,
                                                                                                 segment_number))
                        config_dash.LOG.info(
                            "MCOM-refined results: Adaptation set id {} -> bitrate = {}".format(mcom_adaptationSetIdx,
                                                                                                mcom_current_bitrate))
                    elif playback_type.upper() == "BOLA":
                        current_bitrate = bola_paper.bola_dash(segment_number, dash_player, bitrates, average_dwn_time,
                                                              recent_download_sizes, previous_segment_times, current_bitrate)
                        # Replace result with MCOM plugin result
                        mcom_current_bitrate, mcom_adaptationSetIdx, vmaf = mcom_dash.mcom_dash(dp_object, dash_player, last_throughput,
                                                                                                current_bitrate,
                                                                                                adaptationSetIdx,
                                                                                                segment_number)
                                                                                                
                        config_dash.LOG.info("BOLA-DASH: Selected {} for the segment {}".format(current_bitrate,
                                                                                                 segment_number))
                        config_dash.LOG.info(
                            "MCOM-refined results: Adaptation set id {} -> bitrate = {}".format(mcom_adaptationSetIdx,
                                                                                                mcom_current_bitrate))
                    elif playback_type.upper() == "SMART":
                        if not weighted_mean_object:
                            weighted_mean_object = WeightedMean(config_dash.SARA_SAMPLE_COUNT)
                            config_dash.LOG.debug("Initializing the weighted Mean object")
                        # Checking the segment number is in acceptable range
                        if segment_number < len(dp_list) - 1 + dp_object.getAdaptationSetFromId(adaptationSetIdx).video[current_bitrate].start:
                            try:
                                current_bitrate, delay = weighted_dash.weighted_dash(bitrates, dash_player,
                                                                                     weighted_mean_object.weighted_mean_rate,
                                                                                     current_bitrate,
                                                                                     get_segment_sizes(dp_object.getAdaptationSetFromId(adaptationSetIdx),
                                                                                                       segment_number))
                                # Replace result with MCOM plugin result
                                mcom_current_bitrate, mcom_adaptationSetIdx, vmaf = mcom_dash.mcom_dash(dp_object,
                                                                                                        dash_player, last_throughput,
                                                                                                        current_bitrate,
                                                                                                        adaptationSetIdx,
                                                                                                        segment_number)
                                config_dash.LOG.info("MCOM-refined results: Adaptation set id {} -> bitrate = {}".format(
                                    mcom_adaptationSetIdx, mcom_current_bitrate))
                            except IndexError as e:
                                config_dash.LOG.error(e)

                    elif playback_type.upper() == "NETFLIX":
                        config_dash.LOG.info("Playback is NETFLIX")
                        # Calculate the average segment sizes for each bitrate
                        if not average_segment_sizes:
                            average_segment_sizes = get_average_segment_sizes(dp_object.getAdaptationSetFromId(adaptationSetIdx))
                        if segment_number < len(dp_list) - 1 + dp_object.getAdaptationSetFromId(adaptationSetIdx).video[current_bitrate].start:
                            try:
                                if segment_size and segment_download_time:
                                    segment_download_rate = segment_size / segment_download_time
                                else:
                                    segment_download_rate = 0
                                current_bitrate, netflix_rate_map, netflix_state = netflix_dash.netflix_dash(
                                    bitrates, dash_player, segment_download_rate, current_bitrate, average_segment_sizes,
                                    netflix_rate_map, netflix_state)
                                # Replace result with MCOM plugin result
                                mcom_current_bitrate, mcom_adaptationSetIdx, vmaf = mcom_dash.mcom_dash(dp_object, dash_player, last_throughput, current_bitrate, 
                                adaptationSetIdx, segment_number)
                                config_dash.LOG.info("NETFLIX: Next bitrate = {}".format(current_bitrate))
                                config_dash.LOG.info("MCOM-refined results: Adaptation set id {} -> bitrate = {}".format(mcom_adaptationSetIdx, mcom_current_bitrate))
                            except IndexError as e:
                                config_dash.LOG.error(e)
                        else:
                            config_dash.LOG.critical("Completed segment playback for Netflix")
                            break

                    else:
                        config_dash.LOG.error("Unknown playback type:{}. Continuing with basic playback".format(playback_type))
                        current_bitrate, average_dwn_time = basic_dash.basic_dash(segment_number, bitrates, average_dwn_time,
                                                                                  segment_download_time, current_bitrate)
                else:
                    if playback_type.upper() == "BASIC":
                        current_bitrate, average_dwn_time = basic_dash2.basic_dash2(segment_number, bitrates,
                                                                                    average_dwn_time,
                                                                                    recent_download_sizes,
                                                                                    previous_segment_times, current_bitrate)
                                                                                    
                        config_dash.LOG.info("Basic-DASH: Selected {} for the segment {}".format(current_bitrate,
                                                                                                 segment_number))
                    elif playback_type.upper() == "BOLA":
                        current_bitrate = bola_paper.bola_dash(segment_number, dash_player, bitrates, average_dwn_time,
                                                              recent_download_sizes, previous_segment_times, current_bitrate)
                                                              
                        config_dash.LOG.info("BOLA-DASH: Selected {} for the segment {}".format(current_bitrate,
                                                                                                 segment_number))
                    elif playback_type.upper() == "SMART":
                        if not weighted_mean_object:
                            weighted_mean_object = WeightedMean(config_dash.SARA_SAMPLE_COUNT)
                            config_dash.LOG.debug("Initializing the weighted Mean object")
                        # Checking the segment number is in acceptable range
                        if segment_number < len(dp_list) - 1 + dp_object.getAdaptationSetFromId(adaptationSetIdx).video[
                            current_bitrate].start:
                            try:
                                current_bitrate, delay = weighted_dash.weighted_dash(bitrates, dash_player,
                                                                                     weighted_mean_object.weighted_mean_rate,
                                                                                     current_bitrate,
                                                                                     get_segment_sizes(
                                                                                         dp_object.getAdaptationSetFromId(
                                                                                             adaptationSetIdx),
                                                                                         segment_number))
                            except IndexError as e:
                                config_dash.LOG.error(e)

                    elif playback_type.upper() == "NETFLIX":
                        config_dash.LOG.info("Playback is NETFLIX")
                        # Calculate the average segment sizes for each bitrate
                        if not average_segment_sizes:
                            average_segment_sizes = get_average_segment_sizes(
                                dp_object.getAdaptationSetFromId(adaptationSetIdx))
                        if segment_number < len(dp_list) - 1 + dp_object.getAdaptationSetFromId(adaptationSetIdx).video[
                            current_bitrate].start:
                            try:
                                if segment_size and segment_download_time:
                                    segment_download_rate = segment_size / segment_download_time
                                else:
                                    segment_download_rate = 0
                                current_bitrate, netflix_rate_map, netflix_state = netflix_dash.netflix_dash(
                                    bitrates, dash_player, segment_download_rate, current_bitrate, average_segment_sizes,
                                    netflix_rate_map, netflix_state)
                                config_dash.LOG.info("NETFLIX: Next bitrate = {}".format(current_bitrate))
                            except IndexError as e:
                                config_dash.LOG.error(e)
                        else:
                            config_dash.LOG.critical("Completed segment playback for Netflix")
                            break
                    else:
                        config_dash.LOG.error(
                            "Unknown playback type:{}. Continuing with basic playback".format(playback_type))
                        current_bitrate, average_dwn_time = basic_dash.basic_dash(segment_number, bitrates,
                                                                                  average_dwn_time,
                                                                                  segment_download_time, current_bitrate)
        # print(dp_list[segment])
        segment_path = dp_list[segment][adaptationSetIdx][current_bitrate]
        if multi_codec or playback_type.upper() == "MEDUSA":
            if mcom_current_bitrate and mcom_adaptationSetIdx:
                segment_path = dp_list[segment][mcom_adaptationSetIdx][mcom_current_bitrate]
        #print "domain"
        #print domain
        #print "segment"
        #print segment
        #print "current bitrate"
        #print current_bitrate
        #print segment_path
        segment_url = urlparse.urljoin(domain, segment_path)
        #print "segment url"
        #print segment_url
        config_dash.LOG.info("{}: Segment URL = {}".format(playback_type.upper(), segment_url))
        if dash_player.buffer.qsize() > config_dash.MAX_BUFFER_SIZE and delay == 0:
            delay = 1
        if delay:
            delay_start = time.time()
            config_dash.LOG.info("SLEEPING for {} seconds ".format(delay*segment_duration))
            while time.time() - delay_start < (delay * segment_duration):
                time.sleep(1)
            delay = 0
            config_dash.LOG.debug("SLEPT for {} seconds ".format(time.time() - delay_start))
        start_time = timeit.default_timer()
        try:
            #print 'url'
            #print segment_url
            #print 'file'
            #print file_identifier
            segment_dr = download_segment(segment_url, file_identifier)
            if segment_dr is None:
                config_dash.LOG.info("Downloaded failed. Terminating... ")
                continue
            segment_size, segment_filename = segment_dr
            config_dash.LOG.info("{}: Downloaded segment {}".format(playback_type.upper(), segment_url))
        except IOError as e:
            config_dash.LOG.error("Unable to save segment {}".format(e))
            return None
        segment_download_time = timeit.default_timer() - start_time
        previous_segment_times.append(segment_download_time)
        recent_download_sizes.append(segment_size)
        # Updating the JSON information
        segment_name = os.path.split(segment_url)[1]
        if "segment_info" not in config_dash.JSON_HANDLE:
            config_dash.JSON_HANDLE["segment_info"] = list()
        # Add here the metrics for the final log
        if multi_codec or playback_type.upper() == "MEDUSA":
            if mcom_current_bitrate and mcom_adaptationSetIdx:
                config_dash.JSON_HANDLE["segment_info"].append((segment_name, mcom_current_bitrate, dp_object.getAdaptationSetFromId(mcom_adaptationSetIdx).codec, vmaf, segment_size,
                                                        segment_download_time, dp_object.getAdaptationSetFromId(mcom_adaptationSetIdx).video[mcom_current_bitrate].resolution))
        else:
            config_dash.JSON_HANDLE["segment_info"].append((segment_name, current_bitrate, dp_object.getAdaptationSetFromId(adaptationSetIdx).codec, dp_object.getVmafForSegment(adaptationSetIdx, current_bitrate, segment_number), segment_size,
                                                            segment_download_time, dp_object.getAdaptationSetFromId(adaptationSetIdx).video[current_bitrate].resolution))
        total_downloaded += segment_size
        config_dash.LOG.info("{} : The total downloaded = {}, segment_size = {}, segment_number = {}".format(
            playback_type.upper(),
            total_downloaded, segment_size, segment_number))
        if playback_type.upper() == "SMART" and weighted_mean_object:
            weighted_mean_object.update_weighted_mean(segment_size, segment_download_time)

        segment_info = {'playback_length': video_segment_duration,
                        'size': segment_size,
                        'bitrate': current_bitrate,
                        'data': segment_filename,
                        'URI': segment_url,
                        'segment_number': segment_number}
        segment_duration = segment_info['playback_length']
        dash_player.write(segment_info)
        segment_files.append(segment_filename)
        config_dash.LOG.info("Downloaded %s. Size = %s in %s seconds" % (
            segment_url, segment_size, str(segment_download_time)))
        if previous_bitrate:
            if previous_bitrate < current_bitrate:
                config_dash.JSON_HANDLE['playback_info']['up_shifts'] += 1
            elif previous_bitrate > current_bitrate:
                config_dash.JSON_HANDLE['playback_info']['down_shifts'] += 1
            previous_bitrate = current_bitrate
        # Print stats (lastThroughput, safeThroughput, bufferOccupancy)
        last_throughput = segment_size * 8 / 1000 / segment_download_time
        last_buffer_occupancy = dash_player.buffer.qsize() * video_segment_duration
        config_dash.LOG.info("lastThroughput: {:.0f} kbps".format(last_throughput))
        # config_dash.LOG.info("safeThroughput: {} kbps".format(segment_size * 8 / 1000 / segment_download_time))
        config_dash.LOG.info("bufferOccupancy: {:.3f} s".format(last_buffer_occupancy))

    # waiting for the player to finish playing
    while dash_player.playback_state not in dash_buffer.EXIT_STATES:
        time.sleep(1)
    write_json(json_file=config_dash.JSON_LOG)
    write_input_qoe(video_segment_duration, json_file=config_dash.JSON_QOE_INPUT_LOG)
    # write_output_qoe(json_in_file=config_dash.JSON_QOE_INPUT_LOG, json_out_file=config_dash.JSON_QOE_OUTPUT_LOG)
    if not download:
        clean_files(file_identifier)


def get_segment_sizes(dp_object, segment_number):
    """ Module to get the segment sizes for the segment_number
    :param dp_object:
    :param segment_number:
    :return:
    """
    try:
        segment_sizes = dict([(bitrate, dp_object.video[bitrate].segment_sizes[segment_number - 1]) for bitrate in dp_object.video])
    except Exception as e:
        config_dash.LOG.error("Unable to get the segment sizes")
        return None
    config_dash.LOG.debug("The segment sizes of {} are {}".format(segment_number, segment_sizes))
    return segment_sizes


def get_vmafs(dp_object, segment_number):
    """ Module to get the vmafs for the segment_number
    :param dp_object:
    :param segment_number:
    :return:
    """
    vmafs = dict([(bitrate, dp_object.video[bitrate].vmafs[segment_number]) for bitrate in dp_object.video])
    config_dash.LOG.debug("The segment sizes of {} are {}".format(segment_number, vmafs))
    return vmafs


def get_average_segment_sizes(dp_object):
    """
    Module to get the avearge segment sizes for each bitrate
    :param dp_object:
    :return: A dictionary of aveage segment sizes for each bitrate
    """
    average_segment_sizes = dict()
    for bitrate in dp_object.video:
        segment_sizes = dp_object.video[bitrate].segment_sizes
        segment_sizes = [float(i) for i in segment_sizes]
        try:
            average_segment_sizes[bitrate] = sum(segment_sizes)/len(segment_sizes)
        except ZeroDivisionError:
            average_segment_sizes[bitrate] = 0
    config_dash.LOG.info("The avearge segment size for is {}".format(average_segment_sizes.items()))
    return average_segment_sizes


def clean_files(folder_path):
    """
    :param folder_path: Local Folder to be deleted
    """
    if os.path.exists(folder_path):
        try:
            for video_file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, video_file)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            os.rmdir(folder_path)
        except OSError as e:
            config_dash.LOG.info("Unable to delete the folder {}. {}".format(folder_path, e))
        config_dash.LOG.info("Deleted the folder '{}' and its contents".format(folder_path))


def start_playback_all(dp_object, domain):
    """ Module that downloads the MPD-FIle and download all the representations of 
        the Module to download the MPEG-DASH media.
    """
    # audio_done_queue = Queue()
    video_done_queue = Queue()
    processes = []
    file_identifier = id_generator(6)
    config_dash.LOG.info("File Segments are in %s" % file_identifier)
    # for bitrate in dp_object.audio:
    #     # Get the list of URL's (relative location) for the audio
    #     dp_object.audio[bitrate] = read_mpd.get_url_list(bitrate, dp_object.audio[bitrate],
    #                                                      dp_object.playback_duration)
    #     # Create a new process to download the audio stream.
    #     # The domain + URL from the above list gives the
    #     # complete path
    #     # The fil-identifier is a random string used to
    #     # create  a temporary folder for current session
    #     # Audio-done queue is used to exchange information
    #     # between the process and the calling function.
    #     # 'STOP' is added to the queue to indicate the end
    #     # of the download of the sesson
    #     process = Process(target=get_media_all, args=(domain, (bitrate, dp_object.audio),
    #                                                   file_identifier, audio_done_queue))
    #     process.start()
    #     processes.append(process)

    for bitrate in dp_object.video:
        dp_object.video[bitrate] = read_mpd.get_url_list(bitrate, dp_object.video[bitrate],
                                                         dp_object.playback_duration,
                                                         dp_object.video[bitrate].segment_duration, dp_object.video[bitrate].id)
        # Same as download audio
        process = Process(target=get_media_all, args=(domain, (bitrate, dp_object.video),
                                                      file_identifier, video_done_queue))
        process.start()
        processes.append(process)
    for process in processes:
        process.join()
    count = 0
    for queue_values in iter(video_done_queue.get, None):
        bitrate, status, elapsed = queue_values
        if status == 'STOP':
            config_dash.LOG.critical("Completed download of %s in %f " % (bitrate, elapsed))
            config_dash.LOG.critical("Segment %d out of %d " % (count, len(dp_object.video)))
            count += 1
            if count == len(dp_object.video):
                # If the download of all the videos is done the stop the
                config_dash.LOG.critical("Finished download of all video segments")
                break


def create_arguments(parser):
    """ Adding arguments to the parser """
    parser.add_argument('-m', '--MPD',                   
                        help="Url to the MPD File")
    parser.add_argument('-l', '--LIST', help="List all the representations")
    parser.add_argument('-p', '--PLAYBACK', default=DEFAULT_PLAYBACK, help="Playback type (basic, bola, sara, netflix, or all)")
    parser.add_argument('-b', '--BUFFER_SIZE', default=20, help="Buffer size in seconds")
    parser.add_argument('-n', '--SEGMENT_LIMIT', help="The Segment number limit")
    parser.add_argument('-d', '--DOWNLOAD', default=False, help="Keep the video files after playback")
    parser.add_argument('-z', '--MULTI_CODEC', default=False, help="Activate MCOM Plugin")


def main():
    """ Main Program wrapper """
    # configure the log file
    # Create arguments
    parser = ArgumentParser(description='Process Client parameters')
    create_arguments(parser)
    args = parser.parse_args()
    # globals().update(vars(args))
    medusa_mc = False
    if int(args.MULTI_CODEC) == 1:
        medusa_mc = True
    configure_log_file(playback_type=args.PLAYBACK.lower(), multi_codec=args.MULTI_CODEC)
    if medusa_mc:
        config_dash.JSON_HANDLE['playback_type'] = args.PLAYBACK.lower() + "-mcom"
    else:
        config_dash.JSON_HANDLE['playback_type'] = args.PLAYBACK.lower()
    if not args.MPD:
        print("ERROR: Please provide the URL to the MPD file. Try Again..")
        return None
    config_dash.NETFLIX_BUFFER_SIZE_SECONDS = float(args.BUFFER_SIZE)
    config_dash.LOG.info('Settings: multi-codec -> {}, medusa_mc -> {}'.format(args.MULTI_CODEC, medusa_mc))
    config_dash.LOG.info('Downloading MPD file {}'.format(args.MPD))
    # Retrieve the MPD files for the video
    mpd_file = get_mpd(args.MPD)
    domain = get_domain_name(args.MPD)
    dp_object = DashPlayback()
    
    # Reading the MPD file created
    dp_object, video_segment_duration = read_mpd.read_mpd(mpd_file, dp_object)

    # Fix all the maximum buffer sizes to get a fair comparison
    config_dash.BASIC_THRESHOLD = config_dash.NETFLIX_BUFFER_SIZE_SECONDS / video_segment_duration
    # Update maximum buffer size (in segments) based on the maximum buffer size (in seconds) and the video segment duration
    config_dash.NETFLIX_BUFFER_SIZE = config_dash.NETFLIX_BUFFER_SIZE_SECONDS / video_segment_duration
    # Update the value for MAX_BUFFER_SIZE to have a fair comparison between ABR logics
    config_dash.MAX_BUFFER_SIZE = config_dash.NETFLIX_BUFFER_SIZE_SECONDS / video_segment_duration
    if config_dash.NETFLIX_BUFFER_SIZE_SECONDS == 20:
        config_dash.ALPHA_BUFFER_COUNT = 2 
        config_dash.BETA_BUFFER_COUNT = 4
        config_dash.STABLE_BUFFER_TIME = 10
    else:
        config_dash.ALPHA_BUFFER_COUNT = 5
        config_dash.BETA_BUFFER_COUNT = 10
        config_dash.STABLE_BUFFER_TIME = 20
    
    config_dash.LOG.info("The DASH media has {} video adaptations with a total of {} video representations".format(len([aset for aset in dp_object.adaptationSets if aset.mimeType == "video"]), sum([len(aset.video) for aset in dp_object.adaptationSets])))
    if args.LIST:
        # Print the representations and EXIT
        print_representations(dp_object)
        return None
    if "all" in args.PLAYBACK.lower():
        if mpd_file:
            config_dash.LOG.critical("Start ALL Parallel PLayback")
            start_playback_all(dp_object, domain)
    elif "basic" in args.PLAYBACK.lower():
        config_dash.LOG.critical("Started Basic-DASH Playback")
        start_playback_smart(dp_object, domain, "BASIC", medusa_mc, args.DOWNLOAD, video_segment_duration, args.SEGMENT_LIMIT)
    elif "bola" in args.PLAYBACK.lower():
        config_dash.LOG.critical("Started BOLA-DASH Playback")
        start_playback_smart(dp_object, domain, "BOLA", medusa_mc, args.DOWNLOAD, video_segment_duration, args.SEGMENT_LIMIT)
    elif "sara" in args.PLAYBACK.lower():
        config_dash.LOG.critical("Started SARA-DASH Playback")
        start_playback_smart(dp_object, domain, "SMART", medusa_mc, args.DOWNLOAD, video_segment_duration, args.SEGMENT_LIMIT)
    elif "netflix" in args.PLAYBACK.lower():
        config_dash.LOG.critical("Started Netflix-DASH Playback")
        start_playback_smart(dp_object, domain, "NETFLIX", medusa_mc, args.DOWNLOAD, video_segment_duration, args.SEGMENT_LIMIT)
    elif "medusa" in args.PLAYBACK.lower():
        config_dash.LOG.critical("Started MEDUSA-DASH Playback")
        start_playback_smart(dp_object, domain, "MEDUSA", medusa_mc, args.DOWNLOAD, video_segment_duration, args.SEGMENT_LIMIT)
    else:
        config_dash.LOG.error("Unknown Playback parameter {}".format(args.PLAYBACK))
        return None


if __name__ == "__main__":
    sys.exit(main())
