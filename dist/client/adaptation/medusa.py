__author__ = 'danizenzi'

import config_dash


## Check segment number and indexes of VMAF and segment size array -> indexes are 1 or 2 cells further
def get_bitrates_for_mcom(dp_object):
    """
    Fetch the bitrates related to the bitrate level corresponding to current_bitrate for each adaptation set included in dash_playback object
    :param dp_object: dash_plyback object instance
    :param current_bitrate: current bitrate
    :param adaptationSetIdx: id of the adaptation set corresponding to current_bitrate
    :return: bitrates: bitrates dictionary {int(adaptationSetId): int(bitrate)}
    """
    bitrates = dict()
    for adaptation in dp_object.adaptationSets:
        config_dash.LOG.info("Bitrates for adaptation {}: {}".format(adaptation.id, adaptation.video.keys()))
        bitrates[int(adaptation.id)] = list(adaptation.video.keys())
    return bitrates


def get_vmafs_for_mcom(dp_object, segment_number):
    vmafs = dict()
    for adaptation in dp_object.adaptationSets:
        # if len(adaptation.video[(list(adaptation.video.keys())[current_bitrate_idx])].vmafs) == 0:
        #    config_dash.LOG.debug("VMAF value not available for processing. Returning None")
        #    return None
        vmafs[int(adaptation.id)] = dict()
        for bitrate in adaptation.video.keys():
            # bitrate = float(bitrate) / 1000  # Kbps
            try:
                print("Bitrate: {} -> VMAF: {}".format(bitrate, adaptation.video[bitrate].vmafs[segment_number - 1]))
                vmafs[int(adaptation.id)][bitrate] = adaptation.video[bitrate].vmafs[segment_number - 1]
            except Exception as e:
                config_dash.LOG.info("Could not fetch VMAF values. {}".format(e))
                return None
                # vmafs[int(adaptation.id)][bitrate] = None
    return vmafs


def get_segment_sizes_for_mcom(dp_object, segment_number):
    """
    Fetch the segment size related to the bitrate level corresponding to current_bitrate for the current segment_number and each adaptation set included in dash_playback object
    :param dp_object: dash_playback object instance
    :param current_bitrate: current bitrate
    :param adaptationSetIdx: id of the adaptation set corresponding to current_bitrate
    :param segment_number: number of segment in the reproduction timeline
    :return: segment_sizes: segment size dictionary {int(adaptationSetId): float(segment_size)}
    """
    segment_sizes = dict()
    for adaptation in dp_object.adaptationSets:
        segment_sizes[int(adaptation.id)] = dict()
        for bitrate in adaptation.video.keys():
            try:
                print("Bitrate: {} -> Segment Sizes [bits]: {}".format(bitrate, adaptation.video[bitrate].segment_sizes[segment_number - 1]))
                segment_sizes[int(adaptation.id)][bitrate] = adaptation.video[bitrate].segment_sizes[segment_number - 1]
            except Exception as e:
                config_dash.LOG.info("Could not fetch size values. {}".format(e))
                return None
                # segment_sizes[int(adaptation.id)][bitrate] = None
    return segment_sizes


def medusa_dash(dp_object, dash_player, throughput, segment_number):
    """
    Module to predict the next_bitrate using the mcom_dash plugin and the prediction from the previously selected algorithm
    :param dp_object: Main object from the DashPlayback class
    :param curren_bitrate: Bitrate chosen from previously selected algorithm
    :param adaptationSetIdx: The integer id parameter of the active adaptation set
    :param segment_number: The index of the next segment to be requested
    :return: next_bitrate, next_adaptationId
    """

    ladder = get_bitrates_for_mcom(dp_object)
    vmafs = get_vmafs_for_mcom(dp_object, segment_number)
    segment_sizes = get_segment_sizes_for_mcom(dp_object, segment_number)
    
    if not vmafs or not segment_sizes:
        return None, None, None
    
    config = 1
    
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

    config_dash.LOG.info("Segment index = {}".format(segment_number))

    next_bitrate = None
    next_adaptation_id = None
    selVMAF = None
    selSS = None
    
    if dash_player.playback_state == "BUFFERING" or dash_player.buffer.qsize() <= 2:
        alpha = 0.1
                                                                          
    config_dash.LOG.info("MEDUSA parameters => alpha: {}, (1 - alpha): {}".format(alpha, 1 - alpha))
    
    maxVMAF = 0
    maxSS = 0

    for adaptation in ladder:
        # Only AV1
        if int(adaptation) != 4:
            continue
        for bitrate in ladder[adaptation]:
            if segment_sizes[adaptation][bitrate] is None or vmafs[adaptation][bitrate] is None:
                config_dash.LOG.info("Bitrate '{}' from adaptation with id '{}' has no size or VMAF values for segment {}".format(bitrate, adaptation, segment_number))
                continue
                
            if vmafs[adaptation][bitrate] > maxVMAF:
                maxVMAF = vmafs[adaptation][bitrate]
            if segment_sizes[adaptation][bitrate] > maxSS:
                maxSS = segment_sizes[adaptation][bitrate]
            
    # Selected Objective Function
    sel_objFunc = None
                
    for adaptation in ladder:
        # Only AV1
        if int(adaptation) != 4:
            continue
        for bitrate in ladder[adaptation]:
            temp_objFunc = alpha * vmafs[adaptation][bitrate] / maxVMAF - (1 - alpha) * segment_sizes[adaptation][bitrate] / maxSS
                
            config_dash.LOG.info("Bitrate '{}' from adaptation with id '{}': segment size -> {} Bytes, VMAF = {}, Objective Function: {}".format(
                bitrate, adaptation, float(segment_sizes[adaptation][bitrate]) / 8, vmafs[adaptation][bitrate], temp_objFunc))
            
            if sel_objFunc is None:
                next_adaptation_id = adaptation
                next_bitrate = bitrate
                selSS = float(segment_sizes[next_adaptation_id][bitrate])
                selVMAF = float(vmafs[next_adaptation_id][bitrate])
                sel_objFunc = temp_objFunc
            elif temp_objFunc > sel_objFunc:
                if dash_player.buffer.qsize() <= 2:
                    next_adaptation_id = adaptation
                    next_bitrate = bitrate
                    selSS = float(segment_sizes[next_adaptation_id][bitrate])
                    selVMAF = float(vmafs[next_adaptation_id][bitrate])
                    sel_objFunc = temp_objFunc
                    
                elif (float(segment_sizes[adaptation][bitrate]) / 1000) / throughput < dash_player.segment_duration * (dash_player.buffer.qsize() - 2):
                    next_adaptation_id = adaptation
                    next_bitrate = bitrate
                    selSS = float(segment_sizes[next_adaptation_id][bitrate])
                    selVMAF = float(vmafs[next_adaptation_id][bitrate])
                    sel_objFunc = temp_objFunc

    config_dash.LOG.debug("The next_bitrate is assigned as {} from adaptation with id {}".format(next_bitrate, next_adaptation_id))
    config_dash.LOG.info("Expected download time: {}s".format(selSS / 1000 / throughput))
    config_dash.LOG.info("Available time: {}s".format(dash_player.segment_duration * (dash_player.buffer.qsize() - 2)))
    return next_bitrate, next_adaptation_id, selVMAF
