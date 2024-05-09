# Import packages
import os
import mne
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from fooof import FOOOF
from scipy.signal import welch

from fooof.plts.spectra import plot_spectra

from IPython.display import display

# Import functions
#from signal_processing.spectrum import calculate_psd, find_ind_band
#import basic.arrange_files as arrange

def read_files(dir_inprogress,filetype,exclude_subjects=[],verbose=True):
    """
    Get all the (EEG) file directories and subject names.

    Parameters
    ----------
    dir_inprogress: A string with directory to look for files
    filetype: A string with the ending of the files we are looking for (e.g. '.xdf')

    Returns
    -------
    file_dirs: A list of strings with file directories for all the (EEG) files
    subject_names: A list of strings with all the corresponding subject names
    """

    file_dirs = []
    subject_names = []

    for file in os.listdir(dir_inprogress):
        if file.endswith(filetype):
            file_dirs.append(os.path.join(dir_inprogress, file))
            #subject_names.append(os.path.join(file).removesuffix(filetype))
            subject_names.append(file[:-len(filetype)])

    try:
        for excl_sub in exclude_subjects:
            for i in range(len(subject_names)):
                if excl_sub in subject_names[i]:
                    if verbose == True:
                        print('EXCLUDED SUBJECT: ',excl_sub,'in',subject_names[i],'at',file_dirs[i])
                    del subject_names[i]
                    del file_dirs[i]
                    break
    except:
        pass
    
    file_dirs = sorted(file_dirs)
    subject_names = sorted(subject_names)

    if verbose == True:
        print("Files in {} read in: {}".format(dir_inprogress,len(file_dirs)))

    return [file_dirs, subject_names]

def create_results_folders(exp_folder, exp_condition, exp_condition_nback, results_folder='Results', abs_psd=False,
                           rel_psd=False, fooof = False):
    """
    Dummy way to try to pre-create folders for PSD results before exporting them

    Parameters
    ----------
    exp_folder: A string with a relative directory to experiment folder (e.g. 'Eyes Closed\Baseline')
    """

    if abs_psd == True:
        try:
            os.makedirs(os.path.join('{}/{}/{}/Absolute PSD/{}'.format(results_folder, exp_folder, exp_condition, exp_condition_nback)))
        except FileExistsError:
            pass
        
    
    if rel_psd == True:
        try:
            os.makedirs(os.path.join('{}/{}/{}/Relative PSD/{}'.format(results_folder, exp_folder, exp_condition, exp_condition_nback)))
        except FileExistsError:
            pass
    
    if fooof== True:
        try:
            os.makedirs(os.path.join('{}/{}/{}/FOOOF/{}'.format(results_folder, exp_folder, exp_condition, exp_condition_nback)))
        except FileExistsError:
            pass
    
    try:
        os.makedirs(os.path.join('{}/{}'.format(results_folder, exp_folder)))
    except FileExistsError:
        pass

def calculate_psd(epochs, subjectname, fminmax=[1,50], method="welch",window="hamming", 
                  window_duration=2, window_overlap=0.5,zero_padding=3, tminmax=[None,None],
                  verbose = False, plot = True):
    """
    Calculate power spectrum density with FFT/Welch's method and plot the result.

    Parameters
    ----------
    epochs: Epochs type (MNE-Python) EEG file
    fminfmax: The minimum and maximum frequency range for estimating Welch's PSD
    window: The window type for estimating Welch's PSD
    window_duration: An integer for the length of the window
    window_overlap: A float for the percentage of window size for overlap between te windows 
    zero-padding: A float for coefficient times window size for zero-pads
    tminmax : A list of first and last timepoint of the epoch to include; uses all epochs by default


    Returns
    -------
    psds: An array for power spectrum density values 
    freqs: An array for the corresponding frequencies 

    """
    # Calculate window size in samples and window size x coefs for overlap and zero-pad
    window_size = int(epochs.info["sfreq"]*window_duration)
    n_overlap = int(window_size*window_overlap)
    n_zeropad = int(window_size*zero_padding)

    # N of samples from signals equals to window size
    n_per_seg = window_size

    # N of samples for FFT equals N of samples + zero-padding samples
    n_fft = n_per_seg + n_zeropad

    # Calculate PSD with Welch's method
    spectrum = epochs.compute_psd(method=method, fmin = fminmax[0], fmax = fminmax[1],
                                  n_fft=n_fft, n_per_seg=n_per_seg, n_overlap=n_overlap,
                                  window=window, tmin=tminmax[0], tmax=tminmax[1],
                                  verbose=False)
    
    psds, freqs = spectrum.get_data(return_freqs = True)

    # Unit conversion from V^2/Hz to uV^2/Hz
    psds = psds*1e12

    return [psds, freqs]

def find_ind_band(spectrum, freqs, freq_interest=[4, 8], bw_size=4):
    # Get indexes of band of interest
    freq_interest_idx = np.where(np.logical_and(freqs>=freq_interest[0],
                        freqs<=freq_interest[1]))
    
    # Find maximum amplitude (peak width) in that bandwidth
    pw = np.max(spectrum[freq_interest_idx])

    # Find center frequency index and value where the peak is
    cf_idx = np.where(spectrum == pw)
    cf = float(freqs[cf_idx])
    
    # Get bandwidth range for the band np.round(bw[0], 4)
    bw = [np.round(cf-bw_size/2, 4), np.round(cf+bw_size/2, 4)]

    # Find individual bandpower indexes based on the binsize
    bp_idx = np.logical_and(freqs>=bw[0], freqs<=bw[1])

    # Average the PSD values in these indexes together to get bandpower
    abs_bp = spectrum[bp_idx].mean()

    # Calculate relative bandpower
    rel_bp = abs_bp / spectrum.mean()

    return cf, pw, bw, abs_bp, rel_bp

# Set default directory
os.chdir("/Users/adriana/Documents/GitHub/thesis/MasterThesis/")
mne.set_log_level('error')

# Folder where to get the clean epochs files
clean_folder = "/Users/adriana/Documents/DTU/thesis/data_acquisition/clean_eeg_epoch/"

# Folder where to save the results
results_foldername = "/Users/adriana/Documents/DTU/thesis/data_processing/Results_EEG/"

exp_folder = 'healthy_controls'
exp_condition = 'n_back'
exp_condition_nback = '0_back'
exp_condition_nback_num = 0

# Power spectra estimation parameters
psd_params = dict(method='welch', fminmax=[1, 30], window='hamming', window_duration=2,
                  window_overlap=0.25, zero_padding=39)

# FOOOF (specparam) model parameters
fooof_params = dict(peak_width_limits=[1,12], max_n_peaks=float('inf'), min_peak_height=0.225,
                    peak_threshold=2.0, aperiodic_mode='fixed')

# Band power of interest
# Band power of interest
bands = {'Theta' : [4, 8]}

# Flattened spectra amplitude scale (linear, log)
flat_spectr_scale = 'log'

# Plot more information on the model fit plots or not; and save these plots or not
plot_rich = True
savefig = False

# Get directories of clean EEG files and set export directory
dir_inprogress = os.path.join(clean_folder, exp_folder, exp_condition, exp_condition_nback)
file_dirs, subject_names = read_files(dir_inprogress,'_clean-epo.fif')

# Pre-create results folders for spectral analysis data
create_results_folders(exp_folder=exp_folder, results_folder=results_foldername, 
                       exp_condition_nback=exp_condition_nback, exp_condition=exp_condition, fooof=True)

# Go through all the files (subjects) in the folder

for i in range(len(file_dirs)):
    # Read the clean data from the disk
    epochs = mne.read_epochs(fname='{}/{}_clean-epo.fif'.format(dir_inprogress, subject_names[i]),
                                                                verbose=False)

    """# Create a 3-D array
    data = epochs.get_data(units="uV")
    sf = epochs.info['sfreq']

    win = int(4 * sf)  # Window size is set to 4 seconds
    freqs, psd = welch(data, sf, nperseg=win, axis=-1)"""

    # Calculate Welch's power spectrum density (FFT) -> (epochs, channels, freq bins) shape
    [psds, freqs] = calculate_psd(epochs, subject_names[i], **psd_params, verbose=True, plot=False)
    
    print("This is the shape of psds", psds.shape)
    print("This is the shape of freqs", freqs.shape)

    fm = FOOOF(**fooof_params, verbose = True)
    fm.fit(freqs, psds, psd_params['fminmax'])
    
    # Log-linear conversion based on the chosen amplitude scale
    if flat_spectr_scale == 'linear':
        flatten_spectrum = 10 ** fm._spectrum_flat
        flat_spectr_ylabel = 'Amplitude (uV\u00b2/Hz)'
    elif flat_spectr_scale == 'log':
        flatten_spectrum = fm._spectrum_flat
        flat_spectr_ylabel = 'Log-normalised amplitude'

    # Find individual alpha band parameters
    cf, pw, bw, abs_bp, rel_bp = find_ind_band(flatten_spectrum, freqs,
                                                   bands['Theta'], bw_size=4)
    
    # Set plot styles
    data_kwargs = {'color' : 'black', 'linewidth' : 1.4,
                       'label' : 'Original'}
    model_kwargs = {'color' : 'red', 'linewidth' : 1.4, 'alpha' : 0.75,
                        'label' : 'Full model'}
    aperiodic_kwargs = {'color' : 'blue', 'linewidth' : 1.4, 'alpha' : 0.75,
                            'linestyle' : 'dashed', 'label' : 'Aperiodic model'}
    flat_kwargs = {'color' : 'black', 'linewidth' : 1.4}
    hvline_kwargs = {'color' : 'blue', 'linewidth' : 1.0, 'linestyle' : 'dashed', 'alpha' : 0.75}

    # Plot power spectrum model + aperiodic fit
    fig, axs = plt.subplots(nrows=1, ncols=2, figsize=(10, 4), dpi=150)
    plot_spectra(fm.freqs, fm.power_spectrum, ax = axs[0], **data_kwargs)
    plot_spectra(fm.freqs, fm.fooofed_spectrum_, ax=axs[0], **model_kwargs)
    plot_spectra(fm.freqs, fm._ap_fit,ax=axs[0], **aperiodic_kwargs)
    axs[0].set_xlim(psd_params['fminmax'])
    axs[0].grid(linewidth=0.2)
    axs[0].set_xlabel('Frequency (Hz)')
    axs[0].set_ylabel('Log-normalised amplitude')
    axs[0].set_title('Spectrum model fit')
    axs[0].legend()

    # Flattened spectrum plot (i.e., minus aperiodic fit)
    plot_spectra(fm.freqs, flatten_spectrum,
                      ax=axs[1], **flat_kwargs)
    axs[1].plot(cf, pw, '*', color='blue', label='{} peak'.format(list(bands.keys())[0]))
    axs[1].set_xlim(psd_params['fminmax'])
    axs[1].axvline(x=cf, ymin=0, ymax=pw/(pw*1.1), **hvline_kwargs)
    axs[1].axhline(y=pw, xmin=0, xmax=cf/(psd_params['fminmax'][1]+1))
    axs[1].axvspan(bw[0], bw[1], alpha=0.1, color='green', label='{} band'.format(list(bands.keys())[0]))
    axs[1].grid(linewidth=0.2)
    axs[1].set_xlabel('Frequency (Hz)')
    axs[1].set_ylabel(flat_spectr_ylabel)
    axs[1].set_title('Flattened spectrum')
    axs[1].legend()

    # If true, plot all the exported variables on the plots
    if plot_rich == True:
        axs[0].annotate('Error: ' + str(np.round(fm.get_params('error'), 4)) +
                        '\nR\u00b2: ' + str(np.round(fm.get_params('r_squared'), 4)),
                        (0.1, 0.16), xycoords='figure fraction', color='red', fontsize=8.5)
        axs[0].annotate('Exponent: ' + str(np.round(fm.get_params('aperiodic_params','exponent'), 4)) +
                        '\nOffset: ' + str(np.round(fm.get_params('aperiodic_params','offset'), 4)),
                        (0.19, 0.16), xycoords='figure fraction', color='blue', fontsize=8.5)
        axs[1].text(cf+1, pw, 'CF: '+str(np.round(cf, 4))+'\nPW: '+str(np.round(pw, 4)),
                        verticalalignment='top', color='blue', fontsize=8.5)
        axs[1].annotate('BW: '+str(np.round(bw[0], 4))+' - '+str(np.round(bw[1], 4))+
                            '\nAbs. PSD: '+str(np.round(abs_bp, 4))+'\nRel. PSD: '+str(np.round(rel_bp, 4)),
                            (0.75, 0.16), xycoords='figure fraction', color='green', fontsize=8.5)
        
    plt.show()

"""
        # Add model parameters to dataframe
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'Exponent']\
                                                        = fm.get_params('aperiodic_params','exponent')
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'Offset']\
                                                        = fm.get_params('aperiodic_params','offset')
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'{} CF'.\
                        format(list(bands.keys())[0])] = cf
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'{} PW'.\
                        format(list(bands.keys())[0])] = pw
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'{} BW'.\
                        format(list(bands.keys())[0])] = str(bw)
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'{} absolute power'.\
                        format(list(bands.keys())[0])] = abs_bp
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'{} relative power'.\
                        format(list(bands.keys())[0])] = rel_bp
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'R_2']\
                                                        = fm.get_params('r_squared')
        globals()["df_fooof_"+region].loc[globals()["df_fooof_"+region].index[i],'Error']\
                                                        = fm.get_params('error')

# Export aperiodic data for all regions
for region in df_psds_regions.columns:
    globals()["df_fooof_"+region].to_excel('{}/{}/{}/FOOOF/{}/{}_{}_fooof.xlsx'.format(results_foldername, exp_folder,
                                                                                exp_condition, exp_condition_nback, exp_condition_nback_num, region))
    display(globals()["df_fooof_"+region])
"""