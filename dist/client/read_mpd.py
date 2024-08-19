""" Module for reading the MPD file
    Author: Parikshit Juluri
    Contact : pjuluri@umkc.edu

"""
from __future__ import division
from collections import OrderedDict
import re
import config_dash

FORMAT = 0
URL_LIST = list()
# Dictionary to convert size to bits
SIZE_DICT = {'bits':   1,
             'Kbits':  1024,
             'Mbits':  1024*1024,
             'bytes':  8,
             'KB':  1024*8,
             'MB': 1024*1024*8,
             }
# Try to import the C implementation of ElementTree which is faster
# In case of ImportError import the pure Python implementation
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

MEDIA_PRESENTATION_DURATION = 'mediaPresentationDuration'
MIN_BUFFER_TIME = 'minBufferTime'


class DashPlayback:
    """
    Audio[bandwidth] : {duration, url_list}
    Video[bandwidth] : {duration, url_list}
    """
    def __init__(self):

        self.min_buffer_time = None
        self.playback_duration = None
        self.adaptationSets = []
        # self.audio = dict()
        # self.video = dict()

    def getAdaptationSetFromId(self, adaptationSetId):
        for adaptationSet in self.adaptationSets:
            # print("AdaptationSetId: {} <> SearchedIndex: {}".format(adaptationSet.id, adaptationSetId))
            if str(adaptationSet.id) == str(adaptationSetId):
                return adaptationSet
        return None

    def getVmafForSegment(self, adaptationSetId, current_bitrate, segment_number):
        adaptationSet = self.getAdaptationSetFromId(adaptationSetId)
        if adaptationSet is None:
            return None
        vmaf = None
        try:
            vmaf = adaptationSet.video[current_bitrate].vmafs[segment_number - 1]
        except Exception as e:
            print("VMAF value cannot be retrieved")
        return vmaf


class AdaptationSet(object):
    """Object to handle audio and video adaptation sets """
    """ 
        Audio[bandwidth] : {duration, url_list}
        Video[bandwidth] : {duration, url_list}
    """
    def __init__(self):
        self.audio = OrderedDict()
        self.video = OrderedDict()
        self.mimeType = None
        self.codec = None
        self.id = None


class MediaObject(object):
    """Object to handle audio and video stream """
    def __init__(self):
        self.id = None
        self.codec = None
        self.resolution = None
        self.min_buffer_time = None
        self.start = None
        self.timescale = None
        self.segment_duration = None
        self.initialization = None
        self.base_url = None
        self.segment_sizes = None
        self.vmafs = None
        self.url_list = list()


def get_tag_name(xml_element):
    """ Module to remove the xmlns tag from the name
        eg: '{urn:mpeg:dash:schema:mpd:2011}SegmentTemplate'
             Return: SegmentTemplate
    """
    try:
        tag_name = xml_element[xml_element.find('}')+1:]
    except TypeError:
        config_dash.LOG.error("Unable to retrieve the tag. ")
        return None
    return tag_name


def get_playback_time(playback_duration):
    """ Get the playback time(in seconds) from the string:
        Eg: PT0H1M59.89S
    """
    # Get all the numbers in the string
    numbers = re.split('[PTHMS]', playback_duration)
    # remove all the empty strings
    numbers = [value for value in numbers if value != '']
    numbers.reverse()
    total_duration = 0
    for count, val in enumerate(numbers):
        if count == 0:
            total_duration += float(val)
        elif count == 1:
            total_duration += float(val) * 60
        elif count == 2:
            total_duration += float(val) * 60 * 60
    return total_duration


def get_url_list(media, segment_duration,  playback_duration, bitrate, representationId):
    """
    Module to get the List of URLs
    """
    # Counting the init file
    total_playback = segment_duration
    # print(playback_duration)
    # print(segment_duration)
    segment_count = media.start
    # Get the Base URL string
    base_url = media.base_url
    if "$Bandwidth$" in base_url:
        base_url = base_url.replace("$Bandwidth$", str(bitrate))
    if "$RepresentationID$" in base_url:
        base_url = base_url.replace("$RepresentationID$", str(representationId))
    if "$Number" in base_url:
        base_url = base_url.split('$')
        base_url[1] = base_url[1].replace('$', '')
        base_url[1] = base_url[1].replace('Number', '')
        base_url = ''.join(base_url)
    while True:
        # print(base_url % segment_count)
        media.url_list.append(base_url % segment_count)
        segment_count += 1
        if total_playback >= playback_duration:
            break
        total_playback += segment_duration
    # elif FORMAT == 1:
    #     media.url_list = URL_LIST
    #print media.url_list
    return media


def read_mpd(mpd_file, dashplayback):
    """ Module to read the MPD file"""
    global FORMAT
    config_dash.LOG.info("Reading the MPD file")
    try:
        tree = ET.parse(mpd_file)
    except IOError:
        config_dash.LOG.error("MPD file not found. Exiting")
        return None
    config_dash.JSON_HANDLE["video_metadata"] = {'mpd_file': mpd_file}
    root = tree.getroot()
    if 'MPD' in get_tag_name(root.tag).upper():
        if MEDIA_PRESENTATION_DURATION in root.attrib:
            dashplayback.playback_duration = get_playback_time(root.attrib[MEDIA_PRESENTATION_DURATION])
            config_dash.JSON_HANDLE["video_metadata"]['playback_duration'] = dashplayback.playback_duration
        if MIN_BUFFER_TIME in root.attrib:
            dashplayback.min_buffer_time = get_playback_time(root.attrib[MIN_BUFFER_TIME])
    # format = 0;
    # if "Period" in get_tag_name(root[0].tag):
    #     child_period = root[0]
    #     FORMAT = 0
    # elif "Period" in get_tag_name(root[1].tag):
    #     child_period = root[1]
    #     FORMAT = 1
    #print child_period
    video_segment_duration = None
    # if FORMAT == 0:
    # Print all the information in the MPD
    for node1 in root:
        # print("{} found with following attributes: ".format(get_tag_name(node1.tag)))
        # for att in node1.attrib:
        #     print("\t - {}: {} ".format(att, node1.attrib[att]))
        if get_tag_name(node1.tag) == "Period":
            # print("Period found")
            for node2 in node1:
                # print("\t{} found with following attributes: ".format(get_tag_name(node2.tag)))
                # for att in node2.attrib:
                #     print("\t\t - {}: {} ".format(att, node2.attrib[att]))
                if get_tag_name(node2.tag) == "AdaptationSet":
                    # print("AdaptationSet found")
                    # Node is an AdaptationSet
                    adaptation_set = node2
                    # Create new Adaptation Set
                    adaptationSet = AdaptationSet()
                    if 'id' in adaptation_set.attrib:
                        adaptationSet.id = adaptation_set.attrib['id']
                    media_object = OrderedDict()
                    codec = None
                    mimeType = None
                    for adaptation_set_child in adaptation_set:
                        if get_tag_name(adaptation_set_child.tag) == "Representation":
                            # print("Representation found")
                            representation = adaptation_set_child
                            if 'mimeType' in representation.attrib:
                                media_found = False
                                if 'video' in representation.attrib['mimeType']:
                                    # media_object = dashplayback.video
                                    mimeType = "video"
                                    media_found = True
                                    config_dash.LOG.info("Found Video")
                                elif 'audio' in representation.attrib['mimeType']:
                                    # media_object = dashplayback.audio
                                    mimeType = "audio"
                                    media_found = False
                                    config_dash.LOG.info("Found Audio")
                                    print("Not handling AUDIO at the moment")
                                if media_found:
                                    config_dash.LOG.info("Retrieving Media")
                                    config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'] = list()
                                # print("Media Object is for type {}".format(mimeType))
                                bandwidth = None
                                if 'bandwidth' in representation.attrib:
                                    try:
                                        bandwidth = int(representation.attrib['bandwidth'])
                                    except Exception as e:
                                        print(e)
                                else:
                                    # print("Bandwidth not included in Representation")
                                    continue
                                config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'].append(bandwidth)
                                media_object[bandwidth] = MediaObject()
                                # Check if codec is available
                                if 'codecs' in representation.attrib:
                                    # print("Codec available")
                                    media_object[bandwidth].codec = codec
                                    codec = representation.attrib['codecs']
                                if 'id' in representation.attrib:
                                    # print("RepresentationId available")
                                    media_object[bandwidth].id = representation.attrib['id']
                                if 'width' in representation.attrib and 'height' in representation.attrib:
                                    media_object[bandwidth].resolution = "{}x{}".format(representation.attrib['width'], representation.attrib['height'])
                                # Fetch sizes of segments in SegmentSize nodes
                                media_object[bandwidth].segment_sizes = []
                                # Fetch VMAF values in SegmentSize nodes
                                media_object[bandwidth].vmafs = []
                                for representation_child in representation:
                                    # print("{} found".format(get_tag_name(representation_child.tag)))
                                    if "SegmentTemplate" in get_tag_name(representation_child.tag):
                                        # print("SegmentTemplate found")
                                        segmentTemplate = representation_child
                                        media_object[bandwidth].base_url = segmentTemplate.attrib['media']
                                        media_object[bandwidth].start = int(segmentTemplate.attrib['startNumber'])
                                        media_object[bandwidth].timescale = float(segmentTemplate.attrib['timescale'])
                                        media_object[bandwidth].initialization = segmentTemplate.attrib['initialization']
                                        video_segment_duration = (float(segmentTemplate.attrib['duration']) / float(
                                            segmentTemplate.attrib['timescale']))
                                        config_dash.LOG.debug("Segment Playback Duration = {}".format(video_segment_duration))
                                        for segmentTemplate_child in segmentTemplate:
                                            if "SegmentSize" in get_tag_name(segmentTemplate_child.tag):
                                                # print("SegmentSize found")
                                                try:
                                                    segment_size = float(segmentTemplate_child.attrib['size']) * float(
                                                        SIZE_DICT[segmentTemplate_child.attrib['scale']])
                                                    media_object[bandwidth].segment_sizes.append(segment_size)
                                                except Exception as e:
                                                    config_dash.LOG.error("Error in reading Segment sizes :{}".format(e))
                                                    continue
                                                try:
                                                    vmaf = float(segmentTemplate_child.attrib['vmaf'])
                                                    media_object[bandwidth].vmafs.append(vmaf)
                                                except Exception as e:
                                                    config_dash.LOG.error("Error in reading VMAF value :{}".format(e))
                                                    continue
                    if mimeType == "video":
                        # print(media_object)
                        adaptationSet.video = media_object
                        # print(adaptationSet.video)
                    elif mimeType == "audio":
                        adaptationSet.audio = media_object
                    adaptationSet.mimeType = mimeType
                    adaptationSet.codec = codec
                    dashplayback.adaptationSets.append(adaptationSet)
    #         for node3 in node2:
    #             # print("\t\t{} found with following attributes: ".format(get_tag_name(node3.tag)))
    #             # for att in node3.attrib:
    #             #     print("\t\t\t - {}: {} ".format(att, node3.attrib[att]))
    #             if get_tag_name(node3.tag) == "Representation":
    #                 print("Representation found")
    #             for node4 in node3:
    #                 # print("\t\t\t{} found with following attributes: ".format(get_tag_name(node4.tag)))
    #                 # for att in node4.attrib:
    #                 #     print("\t\t\t\t - {}: {} ".format(att, node4.attrib[att]))
    #                 if get_tag_name(node4.tag) == "SegmentTemplate":
    #                     print("SegmentTemplate found")
    #                 for node5 in node4:
    #                     # print("\t\t\t{} found with following attributes: ".format(get_tag_name(node5.tag)))
    #                     # for att in node5.attrib:
    #                     #     print("\t\t\t\t - {}: {} ".format(att, node5.attrib[att]))
    #                     if get_tag_name(node5.tag) == "SegmentSize":
    #                         print("SegmentSize found")
    # for root_child in root:
    #     print("{} found with following attributes: ".format(get_tag_name(root_child.tag)))
    #     for att in root_child.attrib:
    #         print("\t - {}: {} ".format(att, root_child.attrib[att]))
    #     for adaptation_set in root_child:
    #         if 'mimeType' in adaptation_set.attrib:
    #             media_found = False
    #             if 'audio' in adaptation_set.attrib['mimeType']:
    #                 media_object = dashplayback.audio
    #                 media_found = False
    #                 config_dash.LOG.info("Found Audio")
    #             elif 'video' in adaptation_set.attrib['mimeType']:
    #                 media_object = dashplayback.video
    #                 media_found = True
    #                 config_dash.LOG.info("Found Video")
    #             if media_found:
    #                 config_dash.LOG.info("Retrieving Media")
    #                 config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'] = list()
    #                 for representation in adaptation_set:
    #                     bandwidth = int(representation.attrib['bandwidth'])
    #                     config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'].append(bandwidth)
    #                     media_object[bandwidth] = MediaObject()
    #                     media_object[bandwidth].segment_sizes = []
    #                     for segment_info in representation:
    #                         if "SegmentTemplate" in get_tag_name(segment_info.tag):
    #                             media_object[bandwidth].base_url = segment_info.attrib['media']
    #                             media_object[bandwidth].start = int(segment_info.attrib['startNumber'])
    #                             media_object[bandwidth].timescale = float(segment_info.attrib['timescale'])
    #                             media_object[bandwidth].initialization = segment_info.attrib['initialization']
    #                         if 'video' in adaptation_set.attrib['mimeType']:
    #                             if "SegmentSize" in get_tag_name(segment_info.tag):
    #                                 try:
    #                                     segment_size = float(segment_info.attrib['size']) * float(
    #                                         SIZE_DICT[segment_info.attrib['scale']])
    #                                 except Exception as e:
    #                                     config_dash.LOG.error("Error in reading Segment sizes :{}".format(e))
    #                                     continue
    #                                 media_object[bandwidth].segment_sizes.append(segment_size)
    #                             elif "SegmentTemplate" in get_tag_name(segment_info.tag):
    #                                 video_segment_duration = (float(segment_info.attrib['duration'])/float(
    #                                     segment_info.attrib['timescale']))
    #                                 config_dash.LOG.debug("Segment Playback Duration = {}".format(video_segment_duration))
    #         else:
    #             for representation in adaptation_set:
    #                 media_found = False
    #                 if 'audio' in representation.attrib['mimeType']:
    #                     media_object = dashplayback.audio
    #                     media_found = False
    #                     config_dash.LOG.info("Found Audio")
    #                 elif 'video' in representation.attrib['mimeType']:
    #                     media_object = dashplayback.video
    #                     media_found = True
    #                     config_dash.LOG.info("Found Video")
    #                 if media_found:
    #                     config_dash.LOG.info("Retrieving Media")
    #                     config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'] = list()
    #                 bandwidth = int(representation.attrib['bandwidth'])
    #                 config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'].append(bandwidth)
    #                 media_object[bandwidth] = MediaObject()
    #                 media_object[bandwidth].segment_sizes = []
    #                 media_object[bandwidth].start = int(representation.attrib['startWithSAP'])
    #                 media_object[bandwidth].base_url = root[0].text
    #                 tempcut_url = root[0].text.split('/',3)[2:]
    #                 cut_url = tempcut_url[1]
    #                 print("cut_url = {}".format(cut_url))
    #                 #print root[0].text
    #                 for segment_info in representation:
    #                     if "SegmentBase" in get_tag_name(segment_info.tag):
    #                         for init in segment_info:
    #                             media_object[bandwidth].initialization = cut_url + init.attrib['sourceURL']
    #
    #                     if 'video' in representation.attrib['mimeType']:
    #                         if "SegmentList" in get_tag_name(segment_info.tag):
    #                             video_segment_duration = (float(segment_info.attrib['duration']))
    #                             config_dash.LOG.debug("Segment Playback Duration = {}".format(video_segment_duration))
    #                             for segment_URL in segment_info:
    #                                 if "SegmentURL" in get_tag_name(segment_URL.tag):
    #                                     try:
    #                                         Ssize = segment_URL.attrib['media'].split('/')[0]
    #                                         Ssize = Ssize.split('_')[-1];
    #                                         Ssize = Ssize.split('kbit')[0];
    #                                         #print "ssize"
    #                                         #print Ssize
    #                                         segment_size = float(Ssize) * float(
    #                                             SIZE_DICT["Kbits"])
    #                                     except Exception as e:
    #                                         config_dash.LOG.error("Error in reading Segment sizes :{}".format(e))
    #                                         continue
    #                                     segurl = cut_url + segment_URL.attrib['media']
    #                                     #print segurl
    #                                     URL_LIST.append(segurl)
    #                                     media_object[bandwidth].segment_sizes.append(segment_size)

    # elif FORMAT == 1: #differentFormat
    #
    #     for adaptation_set in child_period:
    #         for representation in adaptation_set:
    #             media_found = False
    #             if 'audio' in representation.attrib['mimeType']:
    #                 media_object = dashplayback.audio
    #                 media_found = False
    #                 config_dash.LOG.info("Found Audio")
    #             elif 'video' in representation.attrib['mimeType']:
    #                 media_object = dashplayback.video
    #                 media_found = True
    #                 config_dash.LOG.info("Found Video")
    #             if media_found:
    #                 config_dash.LOG.info("Retrieving Media")
    #                 config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'] = list()
    #             bandwidth = int(representation.attrib['bandwidth'])
    #             config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'].append(bandwidth)
    #             media_object[bandwidth] = MediaObject()
    #             media_object[bandwidth].segment_sizes = []
    #             media_object[bandwidth].start = int(representation.attrib['startWithSAP'])
    #             media_object[bandwidth].base_url = root[0].text
    #             tempcut_url = root[0].text.split('/',3)[2:]
    #             cut_url = tempcut_url[1]
    #             print("cut_url = {}".format(cut_url))
    #             #print root[0].text
    #             for segment_info in representation:
    #                 if "SegmentBase" in get_tag_name(segment_info.tag):
    #                     for init in segment_info:
    #                         media_object[bandwidth].initialization = cut_url + init.attrib['sourceURL']
    #
    #                 if 'video' in representation.attrib['mimeType']:
    #                     if "SegmentList" in get_tag_name(segment_info.tag):
    #                         video_segment_duration = (float(segment_info.attrib['duration']))
    #                         config_dash.LOG.debug("Segment Playback Duration = {}".format(video_segment_duration))
    #                         for segment_URL in segment_info:
    #                             if "SegmentURL" in get_tag_name(segment_URL.tag):
    #                                 try:
    #                                     Ssize = segment_URL.attrib['media'].split('/')[0]
    #                                     Ssize = Ssize.split('_')[-1];
    #                                     Ssize = Ssize.split('kbit')[0];
    #                                     #print "ssize"
    #                                     #print Ssize
    #                                     segment_size = float(Ssize) * float(
    #                                         SIZE_DICT["Kbits"])
    #                                 except Exception as e:
    #                                     config_dash.LOG.error("Error in reading Segment sizes :{}".format(e))
    #                                     continue
    #                                 segurl = cut_url + segment_URL.attrib['media']
    #                                 #print segurl
    #                                 URL_LIST.append(segurl)
    #                                 media_object[bandwidth].segment_sizes.append(segment_size)

    # elif FORMAT == 2:  # Other format: Period -> AdaptationSet -> {SupplementalProperty, Representation -> {SegmentTemplate: {SegmentSize, ...}}}
    #     for adaptation_set in child_period:
    #         startWithSAP = ""
    #         if "startWithSAP" in adaptation_set.attrib:
    #             startWithSAP = adaptation_set.attrib["startWithSAP"]
    #         # Optional supplemental properties
    #         for adaptation_set_child in adaptation_set:
    #             media = ""
    #             startNumber = ""
    #             timescale = ""
    #             initialization = ""
    #             if "SupplementalProperty" in get_tag_name(adaptation_set_child.tag):
    #                 print("SupplementalProperty found with following attributes: ")
    #                 for att in adaptation_set_child.attrib:
    #                     print("\t - {}: {} ".format(att, adaptation_set_child.attrib[att]))
    #             elif "SegmentTemplate" in get_tag_name(adaptation_set_child.tag):
    #                 print("SegmentTemplate found with following attributes: ")
    #                 for att in adaptation_set_child.attrib:
    #                     print("\t - {}: {} ".format(att, adaptation_set_child.attrib[att]))
    #                 if "SegmentTemplate" in get_tag_name(adaptation_set_child.tag):
    #                     # media_object[bandwidth].base_url = adaptation_set_child.attrib['media']
    #                     # media_object[bandwidth].start = int(adaptation_set_child.attrib['startNumber'])
    #                     # media_object[bandwidth].timescale = float(adaptation_set_child.attrib['timescale'])
    #                     # media_object[bandwidth].initialization = adaptation_set_child.attrib['initialization']
    #                     if "media" in adaptation_set_child.attrib:
    #                         media = adaptation_set_child.attrib['media']
    #                     if "startNumber" in adaptation_set_child.attrib:
    #                         startNumber = adaptation_set_child.attrib['startNumber']
    #                     if "timescale" in adaptation_set_child.attrib:
    #                         timescale = adaptation_set_child.attrib['timescale']
    #                     if "initialization" in adaptation_set_child.attrib:
    #                         initialization = adaptation_set_child.attrib['initialization']
    #             elif "Representation" in get_tag_name(adaptation_set_child.tag):
    #                 media_found = False
    #                 if 'audio' in adaptation_set_child.attrib['mimeType']:
    #                     media_object = dashplayback.audio
    #                     media_found = False
    #                     config_dash.LOG.info("Found Audio")
    #                 elif 'video' in adaptation_set_child.attrib['mimeType']:
    #                     media_object = dashplayback.video
    #                     media_found = True
    #                     config_dash.LOG.info("Found Video")
    #                 else:
    #                     print("Error: MediaType is neither 'video' nor 'audio'")
    #                     continue
    #                 if media_found:  # Video found
    #                     config_dash.LOG.info("Retrieving Media")
    #                     config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'] = list()
    #                 bandwidth = int(adaptation_set_child.attrib['bandwidth'])
    #                 config_dash.JSON_HANDLE["video_metadata"]['available_bitrates'].append(bandwidth)
    #                 media_object[bandwidth] = MediaObject()
    #                 media_object[bandwidth].segment_sizes = []
    #                 if "startWithSAP" in adaptation_set_child.attrib:
    #                     media_object[bandwidth].start = int(adaptation_set_child.attrib['startWithSAP'])
    #                 elif startWithSAP != "":
    #                     media_object[bandwidth].start = int(startWithSAP)
    #                 if media == "":
    #                     media_object[bandwidth].base_url = root[0].text
    #                 else:
    #                     media_object[bandwidth].base_url = media
    #                 tempcut_url = media_object[bandwidth].base_url.split('/', 3)[2:]
    #                 print(tempcut_url)
    #                 cut_url = tempcut_url[1]
    #                 print("cut_url = {}".format(cut_url))
    #                 # print root[0].text
    #                 for segment_info in adaptation_set_child:
    #                     if "SegmentBase" in get_tag_name(segment_info.tag):
    #                         for init in segment_info:
    #                             media_object[bandwidth].initialization = cut_url + init.attrib['sourceURL']
    #
    #                     if 'video' in adaptation_set_child.attrib['mimeType']:
    #                         if "SegmentList" in get_tag_name(segment_info.tag):
    #                             video_segment_duration = (float(segment_info.attrib['duration']))
    #                             config_dash.LOG.debug(
    #                                 "Segment Playback Duration = {}".format(video_segment_duration))
    #                             for segment_URL in segment_info:
    #                                 if "SegmentURL" in get_tag_name(segment_URL.tag):
    #                                     try:
    #                                         Ssize = segment_URL.attrib['media'].split('/')[0]
    #                                         Ssize = Ssize.split('_')[-1]
    #                                         Ssize = Ssize.split('kbit')[0]
    #                                         # print "ssize"
    #                                         # print Ssize
    #                                         segment_size = float(Ssize) * float(
    #                                             SIZE_DICT["Kbits"])
    #                                     except Exception as e:
    #                                         config_dash.LOG.error("Error in reading Segment sizes :{}".format(e))
    #                                         continue
    #                                     segurl = cut_url + segment_URL.attrib['media']
    #                                     # print segurl
    #                                     URL_LIST.append(segurl)
    #                                     media_object[bandwidth].segment_sizes.append(segment_size)
    #             else:
    #                 print("{} found with following attributes: ".format(get_tag_name(adaptation_set_child.tag)))
    #                 for att in adaptation_set_child.attrib:
    #                     print("\t - {}: {} ".format(att, adaptation_set_child.attrib[att]))
    #
    #
    #
    # else:
    #
    #     print("Error: UknownFormat of MPD file!")

    return dashplayback, int(video_segment_duration)