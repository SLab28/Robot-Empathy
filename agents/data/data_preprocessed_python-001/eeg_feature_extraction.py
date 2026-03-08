"""
EEG Feature Extraction Module

This module provides feature extraction functionality for preprocessed EEG signals.
It implements the feature extraction algorithms specified in Requirement 2.3:
- frontal_asymmetry: Difference in alpha power (8-13 Hz) between F4 and F3 channels
- alpha_beta_ratio: Ratio of alpha power (8-13 Hz) to beta power (13-30 Hz) in posterior channels
- frontal_theta_proxy: Theta power (4-8 Hz) in frontal channels (Fp1, Fp2)
- frontotemporal_stability: Coherence between frontal (F7, F8) and temporal (T7, T8) channels

The features are extracted from preprocessed 4-second windows (512 samples at 128 Hz).
Uses scipy for spectral analysis (Welch's method for power spectral density, coherence calculations).

Requirements: 2.3
"""

import numpy as np
from scipy import signal
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class FeatureExtractionConfig:
    """
    Configuration for EEG feature extraction.
    
    Attributes:
        sampling_rate: Sampling rate of the EEG data in Hz
        window_size_seconds: Size of the window for feature extraction in seconds
        alpha_band: Tuple of (low, high) frequencies for alpha band in Hz
        beta_band: Tuple of (low, high) frequencies for beta band in Hz
        theta_band: Tuple of (low, high) frequencies for theta band in Hz
        nperseg: Length of each segment for Welch's method (None = use window size)
        noverlap: Number of points to overlap between segments (None = nperseg // 2)
    """
    sampling_rate: int = 128
    window_size_seconds: float = 4.0
    alpha_band: Tuple[float, float] = (8.0, 13.0)
    beta_band: Tuple[float, float] = (13.0, 30.0)
    theta_band: Tuple[float, float] = (4.0, 8.0)
    nperseg: Optional[int] = None
    noverlap: Optional[int] = None


@dataclass
class EEGFeatures:
    """
    Container for extracted EEG features.
    
    Attributes:
        frontal_asymmetry: Difference in alpha power between F4 and F3 (F4 - F3)
        alpha_beta_ratio: Ratio of alpha to beta power in posterior channels
        frontal_theta_proxy: Average theta power in frontal channels (Fp1, Fp2)
        frontotemporal_stability: Average coherence between frontal and temporal channels
    """
    frontal_asymmetry: float
    alpha_beta_ratio: float
    frontal_theta_proxy: float
    frontotemporal_stability: float
    
    def to_dict(self) -> Dict[str, float]:
        """Convert features to dictionary format."""
        return {
            'frontal_asymmetry': self.frontal_asymmetry,
            'alpha_beta_ratio': self.alpha_beta_ratio,
            'frontal_theta_proxy': self.frontal_theta_proxy,
            'frontotemporal_stability': self.frontotemporal_stability
        }


class EEGFeatureExtractor:
    """
    EEG feature extractor using scipy for spectral analysis.
    
    This class extracts four core features from preprocessed EEG data:
    1. Frontal asymmetry (alpha power difference F4 - F3)
    2. Alpha/beta ratio (posterior channels)
    3. Frontal theta proxy (Fp1, Fp2)
    4. Frontotemporal stability (coherence F7/F8 with T7/T8)
    
    Example:
        >>> config = FeatureExtractionConfig()
        >>> extractor = EEGFeatureExtractor(config)
        >>> channels = {"F3": np.random.randn(512), "F4": np.random.randn(512), ...}
        >>> features = extractor.extract_features(channels)
    """
    
    def __init__(self, config: Optional[FeatureExtractionConfig] = None):
        """
        Initialize the EEG feature extractor.
        
        Args:
            config: Feature extraction configuration. If None, uses default configuration.
        """
        self.config = config or FeatureExtractionConfig()
        
        # Set default nperseg and noverlap if not specified
        if self.config.nperseg is None:
            # Use 2-second segments for Welch's method
            self.config.nperseg = int(2.0 * self.config.sampling_rate)
        
        if self.config.noverlap is None:
            # 50% overlap
            self.config.noverlap = self.config.nperseg // 2
    
    def _compute_band_power(
        self,
        channel_data: np.ndarray,
        freq_band: Tuple[float, float]
    ) -> float:
        """
        Compute power in a specific frequency band using Welch's method.
        
        Args:
            channel_data: 1D array of voltage values
            freq_band: Tuple of (low_freq, high_freq) in Hz
        
        Returns:
            Power in the specified frequency band
        """
        # Compute power spectral density using Welch's method
        freqs, psd = signal.welch(
            channel_data,
            fs=self.config.sampling_rate,
            nperseg=self.config.nperseg,
            noverlap=self.config.noverlap,
            scaling='density'
        )
        
        # Find indices corresponding to the frequency band
        freq_mask = (freqs >= freq_band[0]) & (freqs <= freq_band[1])
        
        # Integrate power in the band (trapezoidal integration)
        # np.trapz was renamed to np.trapezoid in NumPy 2.0
        _trapz = getattr(np, 'trapezoid', None) or np.trapz
        band_power = _trapz(psd[freq_mask], freqs[freq_mask])
        
        return band_power
    
    def _compute_coherence(
        self,
        channel1_data: np.ndarray,
        channel2_data: np.ndarray,
        freq_band: Optional[Tuple[float, float]] = None
    ) -> float:
        """
        Compute coherence between two channels.
        
        Args:
            channel1_data: 1D array of voltage values for first channel
            channel2_data: 1D array of voltage values for second channel
            freq_band: Optional frequency band to average coherence over.
                      If None, returns average coherence across all frequencies.
        
        Returns:
            Coherence value (0-1)
        """
        # Compute coherence using Welch's method
        freqs, coherence = signal.coherence(
            channel1_data,
            channel2_data,
            fs=self.config.sampling_rate,
            nperseg=self.config.nperseg,
            noverlap=self.config.noverlap
        )
        
        if freq_band is not None:
            # Average coherence in the specified frequency band
            freq_mask = (freqs >= freq_band[0]) & (freqs <= freq_band[1])
            avg_coherence = np.mean(coherence[freq_mask])
        else:
            # Average coherence across all frequencies
            avg_coherence = np.mean(coherence)
        
        return avg_coherence
    
    def extract_frontal_asymmetry(
        self,
        channels: Dict[str, np.ndarray]
    ) -> Optional[float]:
        """
        Extract frontal asymmetry feature.
        
        Frontal asymmetry is the difference in alpha power (8-13 Hz) between
        F4 (right) and F3 (left) channels: F4_alpha - F3_alpha
        
        Related to approach/withdrawal motivation and valence.
        Positive values indicate greater right hemisphere activity (withdrawal),
        negative values indicate greater left hemisphere activity (approach).
        
        Args:
            channels: Dictionary mapping channel names to voltage arrays
        
        Returns:
            Frontal asymmetry value, or None if required channels are missing
        """
        if 'F3' not in channels or 'F4' not in channels:
            return None
        
        # Compute alpha power in F3 and F4
        f3_alpha = self._compute_band_power(channels['F3'], self.config.alpha_band)
        f4_alpha = self._compute_band_power(channels['F4'], self.config.alpha_band)
        
        # Frontal asymmetry: F4 - F3 (right - left)
        asymmetry = f4_alpha - f3_alpha
        
        return asymmetry
    
    def extract_alpha_beta_ratio(
        self,
        channels: Dict[str, np.ndarray]
    ) -> Optional[float]:
        """
        Extract alpha/beta ratio feature.
        
        Alpha/beta ratio is the ratio of alpha power (8-13 Hz) to beta power (13-30 Hz)
        in posterior channels (P3, P4, Pz, O1, O2).
        
        Related to arousal and alertness.
        Higher values indicate more relaxed/drowsy state,
        lower values indicate more alert/active state.
        
        Args:
            channels: Dictionary mapping channel names to voltage arrays
        
        Returns:
            Alpha/beta ratio value, or None if no posterior channels are available
        """
        posterior_channels = ['P3', 'P4', 'Pz', 'O1', 'O2']
        available_posterior = [ch for ch in posterior_channels if ch in channels]
        
        if not available_posterior:
            return None
        
        # Compute alpha and beta power for each available posterior channel
        alpha_powers = []
        beta_powers = []
        
        for ch_name in available_posterior:
            alpha_power = self._compute_band_power(channels[ch_name], self.config.alpha_band)
            beta_power = self._compute_band_power(channels[ch_name], self.config.beta_band)
            
            alpha_powers.append(alpha_power)
            beta_powers.append(beta_power)
        
        # Average across channels
        avg_alpha = np.mean(alpha_powers)
        avg_beta = np.mean(beta_powers)
        
        # Compute ratio (avoid division by zero)
        if avg_beta == 0:
            return None
        
        ratio = avg_alpha / avg_beta
        
        return ratio
    
    def extract_frontal_theta_proxy(
        self,
        channels: Dict[str, np.ndarray]
    ) -> Optional[float]:
        """
        Extract frontal theta proxy feature.
        
        Frontal theta proxy is the average theta power (4-8 Hz) in frontal channels
        (Fp1, Fp2).
        
        Related to cognitive load and attention.
        Higher values indicate increased cognitive load or attention demands.
        
        Args:
            channels: Dictionary mapping channel names to voltage arrays
        
        Returns:
            Frontal theta proxy value, or None if required channels are missing
        """
        frontal_channels = ['Fp1', 'Fp2']
        available_frontal = [ch for ch in frontal_channels if ch in channels]
        
        if not available_frontal:
            return None
        
        # Compute theta power for each available frontal channel
        theta_powers = []
        
        for ch_name in available_frontal:
            theta_power = self._compute_band_power(channels[ch_name], self.config.theta_band)
            theta_powers.append(theta_power)
        
        # Average across channels
        avg_theta = np.mean(theta_powers)
        
        return avg_theta
    
    def extract_frontotemporal_stability(
        self,
        channels: Dict[str, np.ndarray]
    ) -> Optional[float]:
        """
        Extract frontotemporal stability feature.
        
        Frontotemporal stability is the coherence between frontal (F7, F8) and
        temporal (T7, T8) channels. We compute coherence for all available pairs
        and average them.
        
        Related to trust and emotional stability.
        Higher values indicate more stable/synchronized activity between regions.
        
        Args:
            channels: Dictionary mapping channel names to voltage arrays
        
        Returns:
            Frontotemporal stability value, or None if required channels are missing
        """
        frontal_channels = ['F7', 'F8']
        temporal_channels = ['T7', 'T8']
        
        available_frontal = [ch for ch in frontal_channels if ch in channels]
        available_temporal = [ch for ch in temporal_channels if ch in channels]
        
        if not available_frontal or not available_temporal:
            return None
        
        # Compute coherence for all frontal-temporal pairs
        coherences = []
        
        for frontal_ch in available_frontal:
            for temporal_ch in available_temporal:
                coh = self._compute_coherence(
                    channels[frontal_ch],
                    channels[temporal_ch]
                )
                coherences.append(coh)
        
        # Average across all pairs
        avg_coherence = np.mean(coherences)
        
        return avg_coherence
    
    def extract_features(
        self,
        channels: Dict[str, np.ndarray]
    ) -> EEGFeatures:
        """
        Extract all four core features from preprocessed EEG data.
        
        Args:
            channels: Dictionary mapping channel names to voltage arrays
        
        Returns:
            EEGFeatures object containing all extracted features
        
        Raises:
            ValueError: If channels is empty or required channels are missing
        """
        if not channels:
            raise ValueError("channels dictionary cannot be empty")
        
        # Extract each feature
        frontal_asymmetry = self.extract_frontal_asymmetry(channels)
        alpha_beta_ratio = self.extract_alpha_beta_ratio(channels)
        frontal_theta_proxy = self.extract_frontal_theta_proxy(channels)
        frontotemporal_stability = self.extract_frontotemporal_stability(channels)
        
        # Check if any features are missing
        missing_features = []
        if frontal_asymmetry is None:
            missing_features.append("frontal_asymmetry (requires F3, F4)")
        if alpha_beta_ratio is None:
            missing_features.append("alpha_beta_ratio (requires P3, P4, Pz, O1, or O2)")
        if frontal_theta_proxy is None:
            missing_features.append("frontal_theta_proxy (requires Fp1 or Fp2)")
        if frontotemporal_stability is None:
            missing_features.append("frontotemporal_stability (requires F7, F8, T7, or T8)")
        
        if missing_features:
            raise ValueError(
                f"Cannot extract all features. Missing channels for: {', '.join(missing_features)}"
            )
        
        return EEGFeatures(
            frontal_asymmetry=frontal_asymmetry,
            alpha_beta_ratio=alpha_beta_ratio,
            frontal_theta_proxy=frontal_theta_proxy,
            frontotemporal_stability=frontotemporal_stability
        )
    
    def __repr__(self) -> str:
        return (
            f"EEGFeatureExtractor("
            f"alpha={self.config.alpha_band} Hz, "
            f"beta={self.config.beta_band} Hz, "
            f"theta={self.config.theta_band} Hz, "
            f"fs={self.config.sampling_rate} Hz)"
        )


def extract_eeg_features(
    channels: Dict[str, np.ndarray],
    config: Optional[FeatureExtractionConfig] = None
) -> EEGFeatures:
    """
    Convenience function to extract EEG features from a window.
    
    Args:
        channels: Dictionary mapping channel names to voltage arrays
        config: Feature extraction configuration. If None, uses default configuration.
    
    Returns:
        EEGFeatures object containing all extracted features
    
    Example:
        >>> channels = {
        ...     "F3": np.random.randn(512), "F4": np.random.randn(512),
        ...     "Fp1": np.random.randn(512), "Fp2": np.random.randn(512),
        ...     "P3": np.random.randn(512), "P4": np.random.randn(512),
        ...     "F7": np.random.randn(512), "F8": np.random.randn(512),
        ...     "T7": np.random.randn(512), "T8": np.random.randn(512)
        ... }
        >>> features = extract_eeg_features(channels)
    """
    extractor = EEGFeatureExtractor(config)
    return extractor.extract_features(channels)
