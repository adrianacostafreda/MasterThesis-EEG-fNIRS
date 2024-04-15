import mne
import numpy as np
import matplotlib.pyplot as plt
import os
from mnelab.io.xdf import read_raw_xdf
from autoreject import AutoReject
from pyprep import NoisyChannels
from mne.preprocessing import ICA
from mne_icalabel import label_components

"""

 -----------------------Reading EEG data----------------------------------------------------------------

"""

def get_raw_from_xdf(xdf_file_path: str) -> mne.io.Raw:
    """This function loads an XDF EEG file, and returns a mne.io.Raw object
    
    Parameters
    ----------
    xdf_file_path : str
        Path to the XDF file. 
    
    """

    raw = read_raw_xdf(xdf_file_path, stream_ids = [1,2], fs_new=500)

    # Drop channels which are not needed for the analysis
    for i in raw.info["ch_names"]: 
        if i in  ["ACC_X","ACC_Y","ACC_Z","Trigger_0", "NIRStarTriggers_0", "NIRStarTriggers_1"]:
            # Drop channels which are not needed for the analysis
            print(i)
            raw.drop_channels(i)
    
    channel_mapping = {"CP5": "FCC1h", "C4":"FFC2h","FC1":"FC3","C3":"FCC3h","T7":"FFC1h","Cz":"FCC2h",
                       "T8":"FCC4h","CP6":"FC4","P9":"CPP3h","Pz":"CCP1h","FC6": "CCP2h",
                       "F10":"CP2","F4":"CPP4h","CP1": "CCP3h","P3":"CP1","FC2":"CCP4h", 
                       "Fp1":"AFp1","Oz":"AFp2","O2":"AFF2h","Fz": "AFF1h",
                         "FC5": "FC5","F9":"FT7","CP2":"FC6","P4":"FT8",
                         "P7": "TP7","Fp2":"TP8", "O1":"P1","F8":"P2","F7": "AFF5h","P8":"AFF6h","F3": "AF7",
                         "P10":"AF8"}
    
    raw.rename_channels(channel_mapping)
    cap_montage = mne.channels.make_standard_montage("brainproducts-RNP-BA-128")

    # Use the preloaded montage
    raw.set_montage(cap_montage)
    
    raw.set_eeg_reference(ref_channels="average")
    
    return raw

"""

 -----------------------Preprocessing----------------------------------------------------------------

"""

def filter_eeg(raw: mne.io.Raw) -> None:
    """
    Preprocess EEG data: filter (bandpass filter between 1 and 50 Hz) and a notch filter at 50 Hz
    """

    raw.filter(l_freq = 1, h_freq = 45, verbose = False)
    
    return raw

def repair_artifacts_ICA(raw_filt):
    
    """
    Use Independent Component Analysis for artifact repair
    """

    # Break raw data into 1 s epochs
    tstep = 1.0
    events_ica = mne.make_fixed_length_events(raw_filt, duration=tstep)
    epochs_ica = mne.Epochs(raw_filt, events_ica,
                    tmin=0.0, tmax=tstep,
                    baseline=None,
                    preload=True)

    ar = AutoReject(n_interpolate=[1, 2, 4],
            random_state=42,
            picks=mne.pick_types(epochs_ica.info, 
                                eeg=True,
                                ),
                n_jobs=-1, 
                verbose=False
                )

    ar.fit(epochs_ica)
    reject_log = ar.get_reject_log(epochs_ica)

    # ICA parameters
    random_state = 42   # ensures ICA is reproducible each time it's run
    ica_n_components = .99     # Specify n_components as a decimal to set % explained variance

    # Fit ICA
    ica = ICA(n_components=ica_n_components,
                random_state=random_state,
                )
    ica.fit(epochs_ica[~reject_log.bad_epochs], decim=3)

    #ica.plot_sources(epochs_ica, block = True)
    #ica.plot_components()
    #plt.show()

    ic_labels = label_components(raw_filt, ica, method="iclabel")

    labels = ic_labels["labels"]
    print(labels)
    
    exclude_idx = [
        idx for idx, label in enumerate(labels) if label in ["eye blink"]
    ]

    print(f"Excluding these ICA components: {exclude_idx}")

    # ica.apply() changes the Raw object in-place, so let's make a copy first:
    reconst_raw = raw_filt.copy()
    ica.apply(reconst_raw, exclude=exclude_idx)

    return reconst_raw

"""
----------Define Epochs-------------------------------

"""

def characterization_trigger_data(raw):
    
    # Dictionary to store trigger data
    trigger_data = {
        '4': {'begin': [], 'end': [], 'duration': []},
        '5': {'begin': [], 'end': [], 'duration': []},
        '6': {'begin': [], 'end': [], 'duration': []},
        '7': {'begin': [], 'end': [], 'duration': []},
        'baseline_0back': {'begin': [], 'end': [], 'duration': []},
        'baseline_1back': {'begin': [], 'end': [], 'duration': []},
        'baseline_2back': {'begin': [], 'end': [], 'duration': []},
        'baseline_3back': {'begin': [], 'end': [], 'duration': []}
    }
    annot = raw.annotations
        
    # Triggers 5, 6 & 7 --> 1-Back Test, 2-Back Test, 3-Back Test
    # Iterate over annotations 
    for idx, desc in enumerate(annot.description):
        if desc in trigger_data:
            begin_trigger = annot.onset[idx]
            duration_trigger = annot.duration[idx] + 60 # Durations of the test are 60 seconds
            end_trigger = begin_trigger + duration_trigger

            # in case the file ends before
            if end_trigger >= raw.times[-1]:
                end_trigger = raw.times[-1]
            else:
                end_trigger = end_trigger
                
            #store trigger data in the dictionary
            trigger_data[desc]["begin"].append(begin_trigger)
            trigger_data[desc]["end"].append(end_trigger)
            trigger_data[desc]["duration"].append(duration_trigger)
    
    #----------------------------------------------------------------------------------

    # Determine the start of trigger 4
    # to set the beginning on Trigger 4, we compute the beginning of Trigger 5 and we subtract the relax
    # period (15s), and the test time (48s) & instructions (8s) of 1-Back Test
    begin_trigger4 = trigger_data["5"]["begin"][0] - 15 - 48 - 8
    trigger_data["4"]["begin"].append(begin_trigger4)
    trigger_data["4"]["duration"].append(48) # Duration of 0-Back Test is 48 s

    end_time = trigger_data["4"]["begin"][0] + 48
    trigger_data["4"]["end"].append(end_time)

    #----------------------------------------------------------------------------------
    
    # Determine the Baseline
    # Begin Baseline
    trigger_data["baseline_0back"]["begin"].append(trigger_data["4"]["end"][0])
    trigger_data["baseline_1back"]["begin"].append(trigger_data["5"]["end"][0])
    trigger_data["baseline_2back"]["begin"].append(trigger_data["6"]["end"][0])
    trigger_data["baseline_3back"]["begin"].append(trigger_data["7"]["end"][0])
    
    # Append 15 s
    trigger_data["baseline_0back"]["duration"].append(15) # Duration of Relax period is 15s
    trigger_data["baseline_1back"]["duration"].append(15) # Duration of Relax period is 15s
    trigger_data["baseline_2back"]["duration"].append(15) # Duration of Relax period is 15s
    trigger_data["baseline_3back"]["duration"].append(15) # Duration of Relax period is 15s

    trigger_data["baseline_0back"]["end"].append(trigger_data["baseline_0back"]["begin"][0] + 15)
    trigger_data["baseline_1back"]["end"].append(trigger_data["baseline_1back"]["begin"][0] + 15)
    trigger_data["baseline_2back"]["end"].append(trigger_data["baseline_2back"]["begin"][0] + 15)
    
    end_baseline_3back = trigger_data["baseline_3back"]["begin"][0] + 15

    if end_baseline_3back >= raw.times[-1]:
        end_baseline_3back = raw.times[-1]
    else:
        end_baseline_3back = end_baseline_3back
    
    trigger_data["baseline_3back"]["end"].append(end_baseline_3back)

    #----------------------------------------------------------------------------------

    # Set new annotations for the current file
    onsets = []
    durations = []
    descriptions = []

    # Accumulate trigger data into lists
    for description, data in trigger_data.items():
        for onset, duration in zip(data["begin"], data["duration"]):
            onsets.append(onset)
            durations.append(duration)
            descriptions.append(description)

    # Create new annotations
    new_annotations = mne.Annotations(
    onsets,
    durations,
    descriptions,
    ch_names=None  # Set to None since annotations don't have associated channel names
    )
    
    raw_new=raw.set_annotations(new_annotations)
    #raw_new.plot(block=True)
    #plt.show()
    
    #----------------------------------------------------------------------------------

    raw_0back = raw_new.copy().crop(tmin=trigger_data['4']['begin'][0], tmax=trigger_data['4']['end'][0])
    raw_1back = raw_new.copy().crop(tmin=trigger_data['5']['begin'][0], tmax=trigger_data['5']['end'][0])
    raw_2back = raw_new.copy().crop(tmin=trigger_data['6']['begin'][0], tmax=trigger_data['6']['end'][0])
    raw_3back = raw_new.copy().crop(tmin=trigger_data['7']['begin'][0], tmax=trigger_data['7']['end'][0])
    raw_baseline_0back = raw_new.copy().crop(tmin=trigger_data['baseline_0back']['begin'][0], tmax=trigger_data['baseline_0back']['end'][0])
    raw_baseline_1back = raw_new.copy().crop(tmin=trigger_data['baseline_1back']['begin'][0], tmax=trigger_data['baseline_1back']['end'][0])
    raw_baseline_2back = raw_new.copy().crop(tmin=trigger_data['baseline_2back']['begin'][0], tmax=trigger_data['baseline_2back']['end'][0])
    raw_baseline_3back = raw_new.copy().crop(tmin=trigger_data['baseline_3back']['begin'][0], tmax=trigger_data['baseline_3back']['end'][0])

    return (raw_0back, raw_1back, raw_2back, raw_3back, raw_baseline_0back, raw_baseline_1back, raw_baseline_2back, raw_baseline_3back)

def epochs_from_raw(raw, raw_0back, raw_1back, raw_2back, raw_3back, raw_baseline_0back, raw_baseline_1back, raw_baseline_2back, raw_baseline_3back):
    """
    Returns a mne.Epochs object created from the annotated mne.io.Raw object.

    """
    # Create epochs of 1 s for all raw segments 
    tstep = 0.8
    events = mne.make_fixed_length_events(raw, duration=tstep)

    interval = (-0.1,0)
    epochs_0back = mne.Epochs(raw_0back, events, tmin=-0.2, tmax=tstep,baseline=interval,preload=True)
    epochs_1back = mne.Epochs(raw_1back, events, tmin=-0.2, tmax=tstep,baseline=interval,preload=True)
    epochs_2back = mne.Epochs(raw_2back, events, tmin=-0.2, tmax=tstep,baseline=interval,preload=True)
    epochs_3back = mne.Epochs(raw_3back, events, tmin=-0.2, tmax=tstep,baseline=interval,preload=True)
    epochs_baseline_0back = mne.Epochs(raw_baseline_0back, events, tmin=-0.2, tmax=tstep,baseline=interval,preload=True)
    epochs_baseline_1back = mne.Epochs(raw_baseline_1back, events, tmin=-0.2, tmax=tstep,baseline=interval,preload=True)
    epochs_baseline_2back = mne.Epochs(raw_baseline_2back, events, tmin=-0.2, tmax=tstep,baseline=interval,preload=True)
    epochs_baseline_3back = mne.Epochs(raw_baseline_3back, events, tmin=-0.2, tmax=tstep,baseline=interval,preload=True)

    #-----------------------Remove Bad Epochs----------------------------------------------------------------
    """

    Remove bad epochs using AutoReject and Rejection Threshold

    """
    
    # -----------------AutoReject---------------------------------
    n_interpolates = np.array([1,4,32])
    consensus_percs = np.linspace(0,1.0,11)

    ar = AutoReject(n_interpolates, consensus_percs, thresh_method = "random_search", random_state = 42)

    epochs_0back_clean, reject_log_0back = ar.fit_transform(epochs_0back, return_log = True)
    epochs_1back_clean, reject_log_1back = ar.fit_transform(epochs_1back, return_log = True)
    epochs_2back_clean, reject_log_2back = ar.fit_transform(epochs_2back, return_log = True)
    epochs_3back_clean, reject_log_3back = ar.fit_transform(epochs_3back, return_log = True)
    epochs_baseline_0back_clean, reject_log_0back_baseline = ar.fit_transform(epochs_baseline_0back, return_log = True)
    epochs_baseline_1back_clean, reject_log_1back_baseline = ar.fit_transform(epochs_baseline_1back, return_log = True)
    epochs_baseline_2back_clean, reject_log_2back_baseline = ar.fit_transform(epochs_baseline_2back, return_log = True)
    epochs_baseline_3back_clean, reject_log_3back_baseline = ar.fit_transform(epochs_baseline_3back, return_log = True)

    return (epochs_0back_clean, epochs_1back_clean, epochs_2back_clean, epochs_3back_clean, 
            epochs_baseline_0back_clean, epochs_baseline_1back_clean, epochs_baseline_2back_clean, epochs_baseline_3back_clean)

mne.set_config("MNE_BROWSER_BACKEND", "qt")
paths = list()

# Read the data hc baseline fnirs
#path_hc_baseline_eeg = "H:\\Dokumenter\\data_processing\\data_eeg\\patients\\baseline\\"
path_hc_baseline_eeg="/Users/adriana/Documents/GitHub/MasterThesis/data/"
folder_hc_baseline_eeg = os.fsencode(path_hc_baseline_eeg)

for file in os.listdir(folder_hc_baseline_eeg):
    filename = os.fsdecode(file)
    if filename.endswith(".xdf"):
        fname = path_hc_baseline_eeg + filename
   
        # --------------Part 1: Read Raw data + Bad channel detection + Filter-------------------
        raw = get_raw_from_xdf(fname)
        raw.load_data()
    
        # --------------Bad Channels--------------------------------

        # use pyprep to get rid of noisy channels and use interpolation
        noisy_channels = NoisyChannels(raw)
        noisy_channels.find_bad_by_deviation() # high/low overall amplitudes
        noisy_channels.find_bad_by_hfnoise() # high-frequenct noise
        bad_channels = noisy_channels.get_bads()
    
        print("Bad channels found by pyprep: ", noisy_channels.get_bads())
        raw.info["bads"]=bad_channels

        # interpolate bad channels
        raw.interpolate_bads(reset_bads=False)

        # --------------Re-referencing EEG channels--------------------------------
        raw = raw.set_eeg_reference(ref_channels="average")
    
        # --------------Filtering--------------------------------
        raw_filt = filter_eeg(raw)

        # --------------ICA artifact------------------------------
        reconst_raw = repair_artifacts_ICA(raw_filt)

        # --------------Raw Segments--------------------------------
        
        raw_characterization = characterization_trigger_data(reconst_raw)

        raw_0back = raw_characterization[0]
        raw_1back = raw_characterization[1]
        raw_2back = raw_characterization[2]
        raw_3back = raw_characterization[3]
        raw_baseline_0back = raw_characterization[4]
        raw_baseline_1back = raw_characterization[5]
        raw_baseline_2back = raw_characterization[6]
        raw_baseline_3back = raw_characterization[7]

        # --------------Epoched Data--------------------------------
        # Each epoched object contains 1s epoched data corresponding to each data segment

        epochs=epochs_from_raw(reconst_raw, raw_0back, raw_1back, raw_2back, raw_3back, raw_baseline_0back, raw_baseline_1back, raw_baseline_2back, raw_baseline_3back)
        
        count=0
        for i in epochs:
            # --------------Save as file--------------------------------
            if count<=3:
                file_name = filename + "_clean-epo" + str(count)+ "back" + ".fif" 
                i.save(file_name, overwrite=True)
                count = count+1
            else:
                file_name = filename + "_clean-epo" + "_baseline_" + str(count)+ "back" + ".fif"
                i.save(file_name, overwrite=True)
                count = count+1