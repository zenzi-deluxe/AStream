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
            print("Adaptation: {} -> {}".format(adaptation.id, adaptation.video[(list(adaptation.video.keys())[current_bitrate_idx])].vmafs))
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
            print("Adaptation: {} -> {}".format(adaptation.id, adaptation.video[(list(adaptation.video.keys())[current_bitrate_idx])].segment_sizes))
            segment_sizes[int(adaptation.id)] = float(adaptation.video[(list(adaptation.video.keys())[current_bitrate_idx])].segment_sizes[segment_number - 1])
        except Exception as e:
            config_dash.LOG.info("Could not fetch segment sizes. {}".format(e))
            # return None
            segment_sizes[int(adaptation.id)] = None
    return segment_sizes


def mcom_dash(dp_object, dash_player, throughput, current_bitrate, adaptationSetIdx, segment_number):
    """
    Module to predict the next_bitrate using the mcom_dash plugin and the prediction from the previously selected algorithm
    :param dp_object: Main object from the DashPlayback class
    :param curren_bitrate: Bitrate chosen from previously selected algorithm
    :param adaptationSetIdx: The integer id parameter of the active adaptation set
    :param segment_number: The index of the next segment to be requested
    :return: next_bitrate, next_adaptationId
    """

    JND_THRESHOLD = 4  # 2

    bitrates = get_bitrates_for_mcom(dp_object, current_bitrate, adaptationSetIdx)
    vmafs = get_vmafs_for_mcom(dp_object, current_bitrate, adaptationSetIdx, segment_number)
    segment_sizes = get_segment_sizes_for_mcom(dp_object, current_bitrate, adaptationSetIdx, segment_number)
    
    config = 0
    
    if config == 1:
        alpha = dash_player.buffer.qsize() / dash_player.max_buffer_size
    elif config == 2:  # Prioritize the quality of the segments
        alpha = 0.8
    elif config == 3:  # Prioritize the size of the segments
        alpha = 0.2
    else:
        alpha = 0.5
    if alpha >= 1:
        alpha = 0.8  # Consider the size, even if minimally

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
        config_dash.LOG.info("Buffer_length = {} Initial Buffer = {} Available video = {} seconds, curr Rate = {}".format(dash_player.buffer.qsize(),
                                                                          dash_player.initial_buffer,
                                                                          available_video_duration, current_bitrate))
                                                                          
        config_dash.LOG.info("MEDUSA parameters => alpha: {}, (1 - alpha): {}".format(alpha, 1 - alpha))

        fixCodecAdaptationId = next_adaptation_id 
        selSS = segment_sizes[next_adaptation_id]
        selVMAF = vmafs[next_adaptation_id]
        next_bitrate = current_bitrate
        selDT = selSS / 1000 / throughput
        fixCodecDT = selDT
        
        maxVMAF = 0
        maxSS = 0

        # Get the maximum values of size and VMAF for the normalization
        for adaptation in dp_object.adaptationSets:

            if segment_sizes[int(adaptation.id)] is None or vmafs[int(adaptation.id)] is None:
                config_dash.LOG.info("Bitrate '{}' from adaptation with id '{}' has no size or VMAF values for segment {}".format(bitrates[int(adaptation.id)], adaptation.id, segment_number))
                continue
                
            if vmafs[int(adaptation.id)] > maxVMAF:
                maxVMAF = vmafs[int(adaptation.id)]
            if segment_sizes[int(adaptation.id)] > maxSS:
                maxSS = segment_sizes[int(adaptation.id)]
            
        # Selected Objective Function
        sel_objFunc = selVMAF # alpha * selVMAF / maxVMAF # - (1 - alpha) * selSS / maxSS
        
        tempVMAF = 0
                
        for adaptation in dp_object.adaptationSets:
        
            temp_objFunc = vmafs[int(adaptation.id)] # alpha * vmafs[int(adaptation.id)] / maxVMAF # - (1 - alpha) * segment_sizes[int(adaptation.id)] / maxSS
            
            tempDT = float(segment_sizes[int(adaptation.id)]) / 1000 / throughput
        
            config_dash.LOG.info("Bitrate '{}' from adaptation with id '{}': segment size -> {} Bytes, VMAF = {}, Estimated Download time: {}s, Objective Function: {}".format(
                bitrates[int(adaptation.id)], adaptation.id, float(segment_sizes[int(adaptation.id)]) / 8, vmafs[int(adaptation.id)], tempDT, temp_objFunc))
        
            if int(adaptation.id) == fixCodecAdaptationId:
                continue           
               
            if dash_player.playback_state == "BUFFERING" or dash_player.buffer.qsize() <= 2:
                # if tempDT < fixCodecDT and float(vmafs[int(adaptation.id)]) >= tempVMAF:
                if tempDT < selDT and selVMAF - float(vmafs[int(adaptation.id)]) <= JND_THRESHOLD:
                    next_adaptation_id = int(adaptation.id)
                    next_bitrate = bitrates[next_adaptation_id]
                    selSS = float(segment_sizes[next_adaptation_id])
                    selVMAF = float(vmafs[next_adaptation_id])
                    # tempVMAF = selVMAF
                    selDT = tempDT
                    sel_objFunc = temp_objFunc
                    config_dash.LOG.info("Changing selection: Buffering or low buffer occupancy")
            else:
                if float(vmafs[int(adaptation.id)]) >= selVMAF and tempDT <= selDT:
                    next_adaptation_id = int(adaptation.id)
                    next_bitrate = bitrates[next_adaptation_id]
                    selSS = float(segment_sizes[next_adaptation_id])
                    selDT = tempDT
                    selVMAF = float(vmafs[next_adaptation_id])
                    sel_objFunc = temp_objFunc
                    config_dash.LOG.info("Changing selection: Normal buffer occupancy")
                # elif float(vmafs[int(adaptation.id)]) - selVMAF >= JND_THRESHOLD and tempDT <= dash_player.segment_duration * (dash_player.buffer.qsize() - 2):
                elif float(vmafs[fixCodecAdaptationId]) - float(vmafs[int(adaptation.id)]) <= JND_THRESHOLD and tempDT < selDT:
                    next_adaptation_id = int(adaptation.id)
                    next_bitrate = bitrates[next_adaptation_id]
                    selDT = tempDT
                    selSS = float(segment_sizes[next_adaptation_id])
                    selVMAF = float(vmafs[next_adaptation_id])
                    sel_objFunc = temp_objFunc
                    config_dash.LOG.info("Changing selection: Normal buffer occupancy")

        config_dash.LOG.debug("The next_bitrate is assigned as {} from adaptation with id {}".format(next_bitrate, next_adaptation_id))
        config_dash.LOG.info("Expected download time: {}s".format(selSS / 1000 / throughput))
        config_dash.LOG.info("Available time: {}s".format(dash_player.segment_duration * (dash_player.buffer.qsize() - 2)))
    return next_bitrate, next_adaptation_id, selVMAF
