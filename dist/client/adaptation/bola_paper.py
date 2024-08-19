__author__ = 'zenzideluxe'

import config_dash
import math
from .basic_dash2 import basic_dash2
import time

bolaState = None

class BolaState:
    """
    Class to manage bola states and parameters
    """
    def __init__(self):
        self.state = None
        self.bitrates = None
        self.utilities = None
        self.Vp = None
        self.gp = None
        self.lastQuality = None

    def initializeBolaState(self, bitrates, stableBufferTime):
        utilities = utilitiesFromBitrates(bitrates)
        utilities = list(map(lambda u: u - utilities[0] + 1, utilities))  # normalize
        # stableBufferTime = getStableBufferTime()
        params = calculateBolaParameters(stableBufferTime, bitrates, utilities)

        if not params:
            # only happens when there is only one bitrate level
            self.state = config_dash.BOLA_STATE_ONE_BITRATE
        else:
            gp, Vp = params
            self.state = config_dash.BOLA_STATE_STARTUP
            self.bitrates = bitrates
            self.utilities = utilities
            self.Vp = Vp
            self.gp = gp
            self.lastQuality = 0


def getThroughput(previous_segment_times, recent_download_sizes):
    # Truncating the list of download times and segment sizes
    while len(previous_segment_times) > config_dash.BASIC_DELTA_COUNT:
        previous_segment_times.pop(0)
    while len(recent_download_sizes) > config_dash.BASIC_DELTA_COUNT:
        recent_download_sizes.pop(0)
    if len(previous_segment_times) == 0 or len(recent_download_sizes) == 0:
        return None

    updated_dwn_time = sum(previous_segment_times) / len(previous_segment_times)

    # Calculate the running download_rate in Kbps for the most recent segments
    return sum(recent_download_sizes) * 8 / (updated_dwn_time * len(previous_segment_times))


def getBolaState(bitrates, stableBufferTime, segmentDuration):
    global bolaState
    if bolaState is None:
        bolaState = BolaState()
        bolaState.initializeBolaState(bitrates, stableBufferTime)
        bolaState.lastSegmentDurationS = segmentDuration
    else:
        if bolaState.lastSegmentDurationS is None:
            bolaState.lastSegmentDurationS = segmentDuration
    return bolaState


def utilitiesFromBitrates(bitrates):
    return list(map(lambda b: math.log(b), bitrates))


def getHighestUtilityIndex(utilities):
    highestUtilityIndex = 0
    for i, u in enumerate(utilities):
        if u > utilities[highestUtilityIndex]:
            highestUtilityIndex = i
    return highestUtilityIndex


def calculateBolaParameters(stableBufferTime, bitrates, utilities):
    highestUtilityIndex = getHighestUtilityIndex(utilities)

    if (highestUtilityIndex == 0):
      # if highestUtilityIndex === 0, then always use lowest bitrate
      return None

    bufferTime = max([stableBufferTime, config_dash.MINIMUM_BUFFER_S + config_dash.MINIMUM_BUFFER_PER_BITRATE_LEVEL_S * len(bitrates)]) # TODO: Investigate if following can be better if utilities are not the default Math.log utilities.
    # If using Math.log utilities, we can choose Vp and gp to always prefer bitrates[0] at minimumBufferS and bitrates[max] at bufferTarget.
    # (Vp * (utility + gp) - bufferLevel) / bitrate has the maxima described when:
    # Vp * (utilities[0] + gp - 1) === minimumBufferS and Vp * (utilities[max] + gp - 1) === bufferTarget
    # giving:
    gp = (utilities[highestUtilityIndex] - 1) / (bufferTime / config_dash.MINIMUM_BUFFER_S - 1)
    Vp = config_dash.MINIMUM_BUFFER_S / gp  # note that expressions for gp and Vp assume utilities[0] === 1, which is true because of normalization
    return gp, Vp


def getQualityFromBufferLevel(bolaState, bufferLevel):
    bitrateCount = len(bolaState.bitrates)
    quality = None
    score = None

    for i in range(bitrateCount):
        s = (bolaState.Vp * (bolaState.utilities[i] + bolaState.gp) - bufferLevel) / bolaState.bitrates[i]
        print("Score for quality {} is {}".format(i, s))

        if score is None or s >= score:
            score = s
            quality = i

        # print("Maximum temp. score is {}".format(score))

    return quality


# maximum buffer level which prefers to download at quality rather than wait
def maxBufferLevelForQuality(bolaState, quality):
    return bolaState.Vp * (bolaState.utilities[quality] + bolaState.gp)


# the minimum buffer level that would cause BOLA to choose quality rather than a lower bitrate
def minBufferLevelForQuality(bolaState, quality):
    qBitrate = bolaState.bitrates[quality]
    qUtility = bolaState.utilities[quality]
    minV = 0

    for i in reversed(range(quality)):
        # for each bitrate less than bitrates[quality], BOLA should prefer quality (unless other bitrate has higher utility)
        if bolaState.utilities[i] < bolaState.utilities[quality]:
            iBitrate = bolaState.bitrates[i]
            iUtility = bolaState.utilities[i]
            level = bolaState.Vp * (bolaState.gp + (qBitrate * iUtility - iBitrate * qUtility) / (qBitrate - iBitrate))
            minV = max([minV, level])  # we want min to be small but at least level(i) for all i

    return minV


def bola_dash(segment_number, dash_player, bitrates, average_dwn_time, recent_download_sizes, previous_segment_times, current_bitrate):
    """
    Module to predict the next_bitrate using the bola_dash algorithm. Selects the bitrate based on Lyapunov optimization.
    :param segment_number: Current segment number
    :param dash_player: Instance of the DashPlayer class
    :param bitrates: A tuple/list of available bitrates
    :param average_dwn_time: Average download time observed so far
    :param segment_download_time:  Time taken to download the current segment
    :return: next_rate : Bitrate for the next segment
    :return: updated_dwn_time: Updated average download time
    """

    throughput = getThroughput(previous_segment_times, recent_download_sizes)

    stableBufferTime = config_dash.STABLE_BUFFER_TIME  # in seconds
    bolaState = getBolaState(bitrates, stableBufferTime, dash_player.segment_duration)

    if bolaState.state == config_dash.BOLA_STATE_ONE_BITRATE:
        # shouldn't even have been called
        return None

    # latency = getAverageLatency(mediaType)
    quality = 0

    bufferLevel = dash_player.buffer.qsize() * dash_player.segment_duration

    if bufferLevel < 2 * dash_player.segment_duration:
        config_dash.LOG.info('BOLA state STARTUP.')
        quality_b, _ = basic_dash2(segment_number, bitrates, average_dwn_time, recent_download_sizes, previous_segment_times, current_bitrate)
        quality = bitrates.index(quality_b)
        bolaState.lastQuality = quality
    else:
        config_dash.LOG.info('BOLA state STEADY.')
        print("Buffer level -> {} s".format(bufferLevel))
        quality = getQualityFromBufferLevel(bolaState, bufferLevel)  # we want to avoid oscillations
        # print("getQualityFromBufferLevel -> {}".format(quality))
        if quality > bolaState.lastQuality:
            m_quality = max([i for i in range(len(bitrates)) if bitrates[i] <= max([throughput, bitrates[0]])])
            if m_quality >= quality:
                m_quality = quality
            elif m_quality < bolaState.lastQuality:
                m_quality = bolaState.lastQuality
            else:
                m_quality += 1
            quality = m_quality

        # TODO Check this delay and the buffer occupancy (max value is not respected)
        delay = max([0, bufferLevel - maxBufferLevelForQuality(bolaState, quality)])  # First reduce placeholder buffer, then tell schedule controller to pause.
        if delay > 0:
            config_dash.LOG.info("Sleeping for {} s".format(delay))
            time.sleep(delay)
        bolaState.lastQuality = quality  # keep bolaState.state === BOLA_STATE_STEADY

    return bitrates[quality]
