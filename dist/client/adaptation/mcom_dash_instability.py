__author__ = 'danizenzi'

import config_dash


## Check segment number and indexes of VMAF and segment size array -> indexes are 1 or 2 cells further
def get_bitrates_for_mcom(dp_object, current_bitrate, adaptationSetIdx):
    """
    Fetch the bitrates related to the bitrate level corresponding to current_bitrate for each adaptation set included in dash_playback object
    :param dp_object: dash_plyback object instance
    :param current_bitrate: current bitrate
    :param adaptationSetIdx: id of the adaptation set corresponding to current_bitrate
    :return: bitrates: bitrates dictionary {int(adaptationSetId): int(bitrate)}
    """
    bitrates = dict()
    current_bitrate_idx = 0
    for adaptation in dp_object.adaptationSets:
        config_dash.LOG.info("Bitrates for adaptation {}: {}".format(adaptation.id, adaptation.video.keys()))
        if int(adaptation.id) == adaptationSetIdx:
            current_bitrate_idx = list(adaptation.video.keys()).index(current_bitrate)
            config_dash.LOG.info("Bitrate index is: {}".format(current_bitrate_idx))
    for adaptation in dp_object.adaptationSets:
        bitrates[int(adaptation.id)] = int(list(adaptation.video.keys())[current_bitrate_idx])
    return bitrates


def get_vmafs_for_mcom(dp_object, current_bitrate, adaptationSetIdx, segment_number):
    vmafs = dict()
    current_bitrate_idx = 0
    for adaptation in dp_object.adaptationSets:
        if int(adaptation.id) == adaptationSetIdx:
            current_bitrate_idx = list(adaptation.video.keys()).index(current_bitrate)
    for adaptation in dp_object.adaptationSets:
        if len(adaptation.video[(list(adaptation.video.keys())[current_bitrate_idx])].vmafs) == 0:
            config_dash.LOG.debug("VMAF value not available for processing. Returning None")
            return None
        try:
            vmafs[int(adaptation.id)] = float(adaptation.video[(list(adaptation.video.keys())[current_bitrate_idx])].vmafs[segment_number - 1])
        except Exception as e:
            config_dash.LOG.info("Could not fetch VMAF values. {}".format(e))
            # return None
            vmafs[int(adaptation.id)] = None
    return vmafs


def get_segment_sizes_for_mcom(dp_object, current_bitrate, adaptationSetIdx, segment_number):
    """
    Fetch the segment size related to the bitrate level corresponding to current_bitrate for the current segment_number and each adaptation set included in dash_playback object
    :param dp_object: dash_playback object instance
    :param current_bitrate: current bitrate
    :param adaptationSetIdx: id of the adaptation set corresponding to current_bitrate
    :param segment_number: number of segment in the reproduction timeline
    :return: segment_sizes: segment size dictionary {int(adaptationSetId): float(segment_size)}
    """
    segment_sizes = dict()
    current_bitrate_idx = 0
    for adaptation in dp_object.adaptationSets:
        if int(adaptation.id) == adaptationSetIdx:
            current_bitrate_idx = list(adaptation.video.keys()).index(current_bitrate)
    for adaptation in dp_object.adaptationSets:
        if len(adaptation.video[(list(adaptation.video.keys())[current_bitrate_idx])].segment_sizes) == 0:
            config_dash.LOG.debug("Segment size value not available for processing. Returning None")
            return None
        try:
            segment_sizes[int(adaptation.id)] = float(adaptation.video[(list(adaptation.video.keys())[current_bitrate_idx])].segment_sizes[segment_number - 1])
        except Exception as e:
            config_dash.LOG.info("Could not fetch segment sizes. {}".format(e))
            # return None
            segment_sizes[int(adaptation.id)] = None
    return segment_sizes


def mcom_dash(dp_object, dash_player, current_bitrate, adaptationSetIdx, segment_number):
    """
    Module to predict the next_bitrate using the mcom_dash plugin and the prediction from the previously selected algorithm
    :param dp_object: Main object from the DashPlayback class
    :param curren_bitrate: Bitrate chosen from previously selected algorithm
    :param adaptationSetIdx: The integer id parameter of the active adaptation set
    :param segment_number: The index of the next segment to be requested
    :return: next_bitrate, next_adaptationId
    """

    JND_THRESHOLD = 2

    bitrates = get_bitrates_for_mcom(dp_object, current_bitrate, adaptationSetIdx)
    vmafs = get_vmafs_for_mcom(dp_object, current_bitrate, adaptationSetIdx, segment_number)
    segment_sizes = get_segment_sizes_for_mcom(dp_object, current_bitrate, adaptationSetIdx, segment_number)

    if not (vmafs[adaptationSetIdx] and segment_sizes[adaptationSetIdx]):
        return current_bitrate, adaptationSetIdx, None

    config_dash.LOG.info("Segment index = {}".format(segment_number))

    next_bitrate = current_bitrate
    next_adaptation_id = adaptationSetIdx
    selVMAF = None
    if bitrates:
        # Waiting time before downloading the next segment
        available_video_segments = dash_player.buffer.qsize() - dash_player.initial_buffer
        # If the buffer is less that the Initial buffer, playback remains at th lowest bitrate
        # i.e dash_buffer.current_buffer < dash_buffer.initial_buffer
        available_video_duration = available_video_segments * dash_player.segment_duration
        config_dash.LOG.debug("Buffer_length = {} Initial Buffer = {} Available video = {} seconds, curr Rate = {}".format(dash_player.buffer.qsize(),
                                                                          dash_player.initial_buffer,
                                                                          available_video_duration, current_bitrate))

        # if weighted_dwn_rate == 0 or available_video_segments == 0:
        #     next_bitrate = bitrates[0]
        # If time to download the next segment with current bitrate is longer than current - initial,
        # switch to a lower suitable bitrate

        selSS = segment_sizes[adaptationSetIdx]
        selVMAF = vmafs[adaptationSetIdx]
        next_bitrate = current_bitrate
        
        previous_vmaf = None
        maxInst = None
        
        # Compute VMAF instability
        if segment_number > 1 and config_dash.JSON_HANDLE["segment_info"][segment_number-1][3]:
            previous_vmaf = config_dash.JSON_HANDLE["segment_info"][segment_number-1][3]  # 3 -> VMAF
            maxInst = abs(selVMAF - previous_vmaf)
        
        maxSS = selSS
        maxVMAF = selVMAF
        for adaptation in dp_object.adaptationSets:
            if segment_sizes[int(adaptation.id)] is None or vmafs[int(adaptation.id)] is None:
                config_dash.LOG.info("Bitrate '{}' from adaptation with id '{}' has no size or VMAF values for segment {}".format(bitrates[int(adaptation.id)], adaptation.id, segment_number))
                continue
            if segment_sizes[int(adaptation.id)] > maxSS:
                maxSS = segment_sizes[int(adaptation.id)]
            if vmafs[int(adaptation.id)] > maxVMAF:
                maxVMAF = vmafs[int(adaptation.id)]
            if maxInst and abs(vmafs[int(adaptation.id)] - previous_vmaf) > maxInst:
                maxInst = abs(vmafs[int(adaptation.id)] - previous_vmaf)
        
        sel_obj_func = selVMAF / maxVMAF - selSS / maxSS
        if maxInst:
            # sel_obj_func = 0.5 * (selVMAF / maxVMAF - (selVMAF - previous_vmaf) / maxInst) - selSS / maxSS
            sel_obj_func -= 0.5 * abs(selVMAF - previous_vmaf) / maxInst

        for adaptation in dp_object.adaptationSets:

            config_dash.LOG.info("Bitrate '{}' from adaptation with id '{}': segment size -> {}, VMAF = {}".format(
                bitrates[int(adaptation.id)], adaptation.id, segment_sizes[int(adaptation.id)], vmafs[int(adaptation.id)]))
                
            temp_obj_func = float(vmafs[int(adaptation.id)]) / maxVMAF - float(segment_sizes[int(adaptation.id)]) / maxSS
            if maxInst:
                # temp_obj_func = 0.5 * (float(vmafs[int(adaptation.id)]) / maxVMAF - (float(vmafs[int(adaptation.id)]) - previous_vmaf) / maxInst) - float(segment_sizes[int(adaptation.id)]) / maxSS
                # config_dash.LOG.info("0.5 * ({} / {} - ({} - {}) / {}) - {} / {} = {}".format(float(vmafs[int(adaptation.id)]), maxVMAF, float(vmafs[int(adaptation.id)]), previous_vmaf, maxInst, float(segment_sizes[int(adaptation.id)]), maxSS, temp_obj_func))
                temp_obj_func -= 0.5 * abs(float(vmafs[int(adaptation.id)]) - previous_vmaf) / maxInst
                config_dash.LOG.info("{} / {} - abs({} - {}) / {} - {} / {} = {}".format(float(vmafs[int(adaptation.id)]), maxVMAF, float(vmafs[int(adaptation.id)]), previous_vmaf, maxInst, float(segment_sizes[int(adaptation.id)]), maxSS, temp_obj_func))
                
            config_dash.LOG.info("Temp. Obj. Func.: {}".format(temp_obj_func))
            
            if temp_obj_func > sel_obj_func:
                next_adaptation_id = int(adaptation.id)
                next_bitrate = bitrates[next_adaptation_id]
                selSS = float(segment_sizes[next_adaptation_id])
                selVMAF = float(vmafs[next_adaptation_id])
                sel_obj_func = temp_obj_func

        config_dash.LOG.debug("The next_bitrate is assigned as {} from adaptation with id {}".format(next_bitrate, next_adaptation_id))
    return next_bitrate, next_adaptation_id, selVMAF
