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
        self.placeholderBuffer = None
        self.bitrates = None
        self.utilities = None
        self.stableBufferTime = None
        self.Vp = None
        self.gp = None
        self.lastQuality = None
        self.mostAdvancedSegmentStart = None
        self.lastSegmentWasReplacement = False
        self.lastSegmentStart = None
        self.lastSegmentDurationS = None
        self.lastSegmentRequestTimeMs = None
        self.lastSegmentFinishTimeMs = None
        self.lastCallTimeMs = None

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
            self.stableBufferTime = stableBufferTime
            self.Vp = Vp
            self.gp = gp
            self.lastQuality = 0
            clearBolaStateOnSeek(self)


def clearBolaStateOnSeek(bolaState):
    bolaState.placeholderBuffer = 0
    bolaState.mostAdvancedSegmentStart = None
    bolaState.lastSegmentWasReplacement = False
    bolaState.lastSegmentStart = None
    bolaState.lastSegmentDurationS = None
    bolaState.lastSegmentRequestTimeMs = None
    bolaState.lastSegmentFinishTimeMs = None
    bolaState.lastCallTimeMs = None


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


def checkBolaStateStableBufferTime(bolaState, stableBufferTime, bufferLevel):
    if bolaState.stableBufferTime != stableBufferTime:
        gp, Vp = calculateBolaParameters(stableBufferTime, bolaState.bitrates, bolaState.utilities)

        if Vp != bolaState.Vp or gp != bolaState.gp:
            # correct placeholder buffer using two criteria:
            # 1. do not change effective buffer level at effectiveBufferLevel === MINIMUM_BUFFER_S ( === Vp * gp )
            # 2. scale placeholder buffer by Vp subject to offset indicated in 1.
            effectiveBufferLevel = bufferLevel + bolaState.placeholderBuffer
            effectiveBufferLevel -= config_dash.MINIMUM_BUFFER_S
            effectiveBufferLevel *= Vp / bolaState.Vp
            effectiveBufferLevel += config_dash.MINIMUM_BUFFER_S
            bolaState.stableBufferTime = stableBufferTime
            bolaState.Vp = Vp
            bolaState.gp = gp
            bolaState.placeholderBuffer = max([0, effectiveBufferLevel - bufferLevel])


def updatePlaceholderBuffer(bolaState, stableBufferTime, bufferLevel):
    nowMs = int(time.time() * 1000)

    if bolaState.lastSegmentFinishTimeMs:
        # compensate for non-bandwidth-derived delays, e.g., live streaming availability, buffer controller
        delay = 0.001 * (nowMs - bolaState.lastSegmentFinishTimeMs)
        bolaState.placeholderBuffer += max([0, delay])
    elif bolaState.lastCallTimeMs:
        # no download after last call, compensate for delay between calls
        _delay = 0.001 * (nowMs - bolaState.lastCallTimeMs)
        bolaState.placeholderBuffer += max([0, _delay])

    bolaState.lastCallTimeMs = nowMs
    bolaState.lastSegmentStart = None
    bolaState.lastSegmentRequestTimeMs = None
    bolaState.lastSegmentFinishTimeMs = None
    checkBolaStateStableBufferTime(bolaState, stableBufferTime, bufferLevel)


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

    stableBufferTime = config_dash.STABLE_BUFFER_TIME  # in seconds
    bolaState = getBolaState(bitrates, stableBufferTime, dash_player.segment_duration)

    if bolaState.state == config_dash.BOLA_STATE_ONE_BITRATE:
        # shouldn't even have been called
        return None

    # latency = getAverageLatency(mediaType)
    quality = 0
    delayS = None

    while delayS != 0:
        bufferLevel = dash_player.buffer.qsize() * dash_player.segment_duration
        if delayS is not None:
            time.sleep(delayS)
        delayS = 0
        if bolaState.state == config_dash.BOLA_STATE_STARTUP:
            config_dash.LOG.info('BOLA state STARTUP.')
            quality_b, _ = basic_dash2(segment_number, bitrates, average_dwn_time, recent_download_sizes, previous_segment_times, current_bitrate)
            quality = bitrates.index(quality_b)
            bolaState.placeholderBuffer = max([0, minBufferLevelForQuality(bolaState, quality) - bufferLevel])
            bolaState.lastQuality = quality

            if bolaState.lastSegmentDurationS and bufferLevel >= bolaState.lastSegmentDurationS:
                bolaState.state = config_dash.BOLA_STATE_STEADY
            # End BOLA_STATE_STARTUP
        elif bolaState.state == config_dash.BOLA_STATE_STEADY:
            config_dash.LOG.info('BOLA state STEADY.')
            # NB: The placeholder buffer is added to bufferLevel to come up with a bitrate.
            #     This might lead BOLA to be too optimistic and to choose a bitrate that would lead to rebuffering -
            #     if the real buffer bufferLevel runs out, the placeholder buffer cannot prevent rebuffering.
            #     However, the InsufficientBufferRule takes care of this scenario.
            print("Buffer level -> {} s".format(bufferLevel))
            updatePlaceholderBuffer(bolaState, stableBufferTime, bufferLevel)
            quality = getQualityFromBufferLevel(bolaState, bufferLevel + bolaState.placeholderBuffer)  # we want to avoid oscillations
            print("getQualityFromBufferLevel -> {}".format(quality))
            # We implement the "BOLA-O" variant: when network bandwidth lies between two encoded bitrate levels, stick to the lowest level.

            quality_b, _ = basic_dash2(segment_number, bitrates, average_dwn_time, recent_download_sizes, previous_segment_times, current_bitrate)
            qualityForThroughput = bitrates.index(quality_b)
            if quality > bolaState.lastQuality and quality > qualityForThroughput:
                # only intervene if we are trying to *increase* quality to an *unsustainable* level
                # we are only avoid oscillations - do not drop below last quality
                quality = max([qualityForThroughput, bolaState.lastQuality])
                print("Final quality -> {}".format(quality))
            # We do not want to overfill buffer with low quality chunks.
            # Note that there will be no delay if buffer level is below MINIMUM_BUFFER_S, probably even with some margin higher than MINIMUM_BUFFER_S.

            # TODO Check this delay and the buffer occupancy (max value is not respected)
            delayS = max([0, bufferLevel + bolaState.placeholderBuffer - maxBufferLevelForQuality(bolaState, quality)])  # First reduce placeholder buffer, then tell schedule controller to pause.

            if (delayS <= bolaState.placeholderBuffer):
                bolaState.placeholderBuffer -= delayS
                delayS = 0
            else:
                delayS -= bolaState.placeholderBuffer
                bolaState.placeholderBuffer = 0

                if quality < qualityForThroughput:
                    # At top quality, allow schedule controller to decide how far to fill buffer.
                    # scheduleController.setTimeToLoadDelay(1000 * delayS)
                    print("scheduleController.setTimeToLoadDelay(1000 * delayS)")
                else:
                    delayS = 0

            bolaState.lastQuality = quality  # keep bolaState.state === BOLA_STATE_STEADY

            # BOLA_STATE_STEADY
        else:
            config_dash.LOG.info('BOLA ABR rule invoked in bad state.')
            quality_b, _ = basic_dash2(segment_number, bitrates, average_dwn_time, recent_download_sizes, previous_segment_times, current_bitrate)
            quality = bitrates.index(quality_b)
            bolaState.state = config_dash.BOLA_STATE_STARTUP
            clearBolaStateOnSeek(bolaState)

    return bitrates[quality]
