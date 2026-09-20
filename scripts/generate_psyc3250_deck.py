"""
PSYC 3250M Midterm Anki Deck Generator
Creates high-quality, differentiated bidirectional flashcards
Based on actual PDF content - no guessing
"""

import genanki
import random
import json
from pathlib import Path

# Load configuration
CONFIG_PATH = Path(__file__).parent.parent / 'config.json'
with open(CONFIG_PATH, 'r') as f:
    CONFIG = json.load(f)

OUTPUT_DIR = Path(CONFIG['output_directory'])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Anki model with clean formatting
ANKI_MODEL = genanki.Model(
    1607392319,
    'PSYC 3250M Model',
    fields=[
        {'name': 'Question'},
        {'name': 'Answer'},
    ],
    templates=[
        {
            'name': 'Card',
            'qfmt': '<div class="question">{{Question}}</div>',
            'afmt': '{{FrontSide}}<hr id="answer"><div class="answer">{{Answer}}</div>',
        },
    ],
    css="""
    .card {
        font-family: Arial, sans-serif;
        font-size: 20px;
        text-align: left;
        color: black;
        background-color: white;
        padding: 20px;
    }
    .question {
        font-weight: bold;
        margin-bottom: 10px;
        line-height: 1.5;
    }
    .answer {
        line-height: 1.6;
        margin-top: 10px;
    }
    hr {
        margin: 20px 0;
    }
    ul, ol {
        margin-left: 20px;
    }
    """
)

def create_bidirectional_cards(deck, question, answer, tags=[]):
    """Create two cards: Q->A and A->Q"""
    # Forward card
    note1 = genanki.Note(
        model=ANKI_MODEL,
        fields=[question, answer],
        tags=tags
    )
    deck.add_note(note1)
    
    # Reverse card
    note2 = genanki.Note(
        model=ANKI_MODEL,
        fields=[answer, question],
        tags=tags + ['reverse']
    )
    deck.add_note(note2)

def main():
    # Create deck
    deck = genanki.Deck(
        random.randrange(1 << 30, 1 << 31),
        'PSYC 3250M - Neural Basis of Behaviour Midterm'
    )
    
    print("Generating cards...")
    
    # ===== NEUROIMAGING TECHNIQUES =====
    
    # Structural MRI
    create_bidirectional_cards(deck,
        "What are the advantages of Structural MRI?",
        "• Good spatial resolution (0.3-3 mm³)<br>• Non-invasive",
        ['neuroimaging', 'MRI', 'structural']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of Structural MRI?",
        "• Cannot be used with people who have metal in their bodies or pacemakers<br>• Expensive (relative to CT)",
        ['neuroimaging', 'MRI', 'structural']
    )
    
    # DTI
    create_bidirectional_cards(deck,
        "What does DTI (Diffusion Tensor Imaging) measure?",
        "Direction of water diffusion in the brain, revealing white matter tracts where diffusion is restricted",
        ['neuroimaging', 'DTI']
    )
    
    create_bidirectional_cards(deck,
        "How long does it take to collect one person's diffusion-weighted image?",
        "15-60 minutes",
        ['neuroimaging', 'DTI']
    )
    
    # PET
    create_bidirectional_cards(deck,
        "What are the advantages of PET?",
        "• Non-invasive technique<br>• Good spatial resolution (voxels ~5-10 mm³)",
        ['neuroimaging', 'PET']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of PET?",
        "• Poor temporal resolution (~1 min at best)<br>• Limited by radioactive agent decay (minutes)",
        ['neuroimaging', 'PET']
    )
    
    create_bidirectional_cards(deck,
        "How does PET work?",
        "Injection of radioactive water containing fast-decaying tracer isotopes (e.g., oxygen-15) into bloodstream; measures where this material accumulates in the brain",
        ['neuroimaging', 'PET']
    )
    
    create_bidirectional_cards(deck,
        "How long does it take to collect one brain volume with PET?",
        "~30 minutes",
        ['neuroimaging', 'PET']
    )
    
    # fMRI - BOLD
    create_bidirectional_cards(deck,
        "What does BOLD stand for in fMRI?",
        "Blood Oxygen Level Dependent",
        ['neuroimaging', 'fMRI', 'BOLD']
    )
    
    create_bidirectional_cards(deck,
        "What does fMRI BOLD measure?",
        "The ratio of oxygenated to deoxygenated blood",
        ['neuroimaging', 'fMRI', 'BOLD']
    )
    
    create_bidirectional_cards(deck,
        "What is the BOLD effect?",
        "As neuronal activity ↑ → blood flow ↑ → blood oxygenation ↑<br>Oxygenated blood is magnetic; deoxygenated blood is paramagnetic",
        ['neuroimaging', 'fMRI', 'BOLD']
    )
    
    create_bidirectional_cards(deck,
        "Why does fMRI BOLD require a baseline condition?",
        "Because BOLD response is a relative signal (units of % signal change), not an absolute measure",
        ['neuroimaging', 'fMRI', 'BOLD']
    )
    
    create_bidirectional_cards(deck,
        "What is the Hemodynamic Response Function (HRF)?",
        "Increase in BOLD signal in response to stimulus and/or neural activation",
        ['neuroimaging', 'fMRI', 'HRF']
    )
    
    # fMRI Designs - Blocked
    create_bidirectional_cards(deck,
        "What are the advantages of blocked fMRI designs?",
        "• High detection power<br>• Most widely used approach<br>• Robust to noise (e.g., slice timing differences)",
        ['neuroimaging', 'fMRI', 'blocked']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of blocked fMRI designs?",
        "• Participant gets into a mental set for a block (assumes continuous engagement)<br>• Very predictable for subject<br>• Cannot look at effects of single events (e.g., correct vs incorrect trials)",
        ['neuroimaging', 'fMRI', 'blocked']
    )
    
    # fMRI Designs - Event-Related
    create_bidirectional_cards(deck,
        "What are the advantages of event-related fMRI designs?",
        "• Complex designs with random task presentations<br>• Can create post-hoc conditions based on behaviour<br>• Can separate overlapping fMRI responses of different trials",
        ['neuroimaging', 'fMRI', 'event-related']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of event-related fMRI designs?",
        "• Reduced detection/power compared to block designs<br>• Accurate detection requires accurate HRF modeling<br>• HRF can differ between brain regions",
        ['neuroimaging', 'fMRI', 'event-related']
    )
    
    # fMRI Analysis Types
    create_bidirectional_cards(deck,
        "What is univariate data analysis in fMRI?",
        "Contrast BOLD response for different conditions in a voxel or ROI",
        ['neuroimaging', 'fMRI', 'analysis', 'univariate']
    )
    
    create_bidirectional_cards(deck,
        "What is functional connectivity analysis?",
        "Correlate BOLD time series of different voxels to identify and characterize brain networks",
        ['neuroimaging', 'fMRI', 'connectivity']
    )
    
    create_bidirectional_cards(deck,
        "What is MVPA (Multi-Voxel Pattern Analysis)?",
        "Use machine learning algorithms to predict (decode) how response patterns across voxels relate to conditions",
        ['neuroimaging', 'fMRI', 'MVPA']
    )
    
    create_bidirectional_cards(deck,
        "What is the difference between univariate and multivariate fMRI analysis?",
        "Univariate: Consider only 1 value per condition (e.g., average signal of voxel or ROI)<br>Multivariate: Consider pattern of responses across multiple voxels per condition",
        ['neuroimaging', 'fMRI', 'analysis']
    )
    
    # Resting State fMRI
    create_bidirectional_cards(deck,
        "What is resting-state fMRI used for?",
        "Measuring spontaneous/intrinsic brain activity with correlated activity within large-scale functional brain networks",
        ['neuroimaging', 'fMRI', 'resting-state']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of fMRI?",
        "• Non-invasive technique<br>• Good spatial resolution (mm)<br>• Adaptable to many experimental designs (block and event-related)<br>• Whole brain imaging allows for connectivity measures",
        ['neuroimaging', 'fMRI']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of fMRI?",
        "• Indirect measure of brain activity/connectivity (measures blood flow not neurons)<br>• Regions of signal dropout at junctions between air and tissue (sinuses, ear canals)<br>• Relatively slow temporal resolution (seconds)",
        ['neuroimaging', 'fMRI']
    )
    
    # MRS
    create_bidirectional_cards(deck,
        "What does MRS (Magnetic Resonance Spectroscopy) measure?",
        "Chemical composition of brain tissue; estimates neurochemical concentrations (e.g., GABA levels, glutamate levels)",
        ['neuroimaging', 'MRS']
    )
    
    create_bidirectional_cards(deck,
        "How long does one large voxel measurement take with MRS?",
        "About 10 minutes",
        ['neuroimaging', 'MRS']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of MRS?",
        "• Non-invasive technique<br>• Insight into neurochemical/neurotransmitter concentrations",
        ['neuroimaging', 'MRS']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of MRS?",
        "• Poor temporal resolution (if any)<br>• Low spatial resolution (multiple cm)",
        ['neuroimaging', 'MRS']
    )
    
    # EEG
    create_bidirectional_cards(deck,
        "What does EEG measure?",
        "Summed electrical activity from many neurons across the scalp (non-invasively)",
        ['neuroimaging', 'EEG']
    )
    
    create_bidirectional_cards(deck,
        "What is the temporal resolution of EEG?",
        "Millisecond time resolution",
        ['neuroimaging', 'EEG']
    )
    
    create_bidirectional_cards(deck,
        "What is the spatial resolution of EEG?",
        "Poor spatial resolution (~5-10 cm)",
        ['neuroimaging', 'EEG']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of EEG?",
        "• Non-invasive technique<br>• Good temporal resolution (milliseconds)<br>• Cheap<br>• Whole brain coverage",
        ['neuroimaging', 'EEG']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of EEG?",
        "• Poor spatial resolution (~5-10 cm)<br>• Difficult to disentangle different signals and their neural origin",
        ['neuroimaging', 'EEG']
    )
    
    # MEG
    create_bidirectional_cards(deck,
        "What does MEG measure?",
        "Summed tiny fluctuations in magnetic fields across the scalp, generated by electrical activity from many neurons (non-invasively)",
        ['neuroimaging', 'MEG']
    )
    
    create_bidirectional_cards(deck,
        "Why does MEG have slightly better spatial resolution than EEG?",
        "Magnetic signals are not affected by passive spread of electrical currents across tissues (volume conduction)",
        ['neuroimaging', 'MEG']
    )
    
    create_bidirectional_cards(deck,
        "What is the spatial resolution of MEG?",
        "~4-8 cm (slightly better than EEG)",
        ['neuroimaging', 'MEG']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of MEG?",
        "• Non-invasive technique<br>• Good temporal resolution (milliseconds)<br>• Slightly better spatial resolution than EEG<br>• Setup is easier (no gel or salt solution needed like for EEG)",
        ['neuroimaging', 'MEG']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of MEG?",
        "• Spatial resolution is still poor (~4-8 cm)<br>• Difficult to disentangle different signals and their neural origin<br>• Expensive",
        ['neuroimaging', 'MEG']
    )
    
    # ECoG/sEEG
    create_bidirectional_cards(deck,
        "What is ECoG (Electrocorticography)?",
        "Direct measurement of electrical activity from the brain surface using grid electrodes placed on the cortex",
        ['neuroimaging', 'ECoG']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of ECoG/sEEG?",
        "• You know where signal is coming from<br>• High temporal resolution (sub-millisecond)<br>• Very little measurement noise",
        ['neuroimaging', 'ECoG']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of ECoG/sEEG?",
        "• No control over electrode placement and experiment time<br>• Brain tissue may be diseased/damaged",
        ['neuroimaging', 'ECoG']
    )
    
    # ERPs and Oscillations
    create_bidirectional_cards(deck,
        "What is an ERP (Event-Related Potential)?",
        "Average of electrical brain response to specific events, repeated over many trials",
        ['neuroimaging', 'ERP']
    )
    
    create_bidirectional_cards(deck,
        "What happens when averaging across trials in ERPs?",
        "May cancel activity that is not phase-locked",
        ['neuroimaging', 'ERP', 'oscillations']
    )
    
    create_bidirectional_cards(deck,
        "What are asynchronous broadband (high gamma) responses in ECoG?",
        "Increase in overall level of response across broad range of frequencies (thought to reflect integration of neural firing by dendrites); not phase-locked or rhythmic; best observed in higher frequencies",
        ['neuroimaging', 'ECoG', 'oscillations']
    )
    
    # ===== NEUROMODULATION =====
    
    # TMS
    create_bidirectional_cards(deck,
        "How does TMS work?",
        "Magnetic field outside skull induces electric field inside skull; magnetic stimulation disrupts normal brain activity, creating a 'virtual lesion'",
        ['neuromodulation', 'TMS']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of TMS?",
        "• Reasonable spatial resolution (1-2 centimeters)<br>• High temporal resolution (sub-millisecond)<br>• Can be used repeatedly<br>• Provides information about causal role of brain area in function",
        ['neuromodulation', 'TMS']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of TMS?",
        "• Restricted to brain regions close to skull<br>• Holding coil in place not easy<br>• Muscle twitches can be uncomfortable",
        ['neuromodulation', 'TMS']
    )
    
    create_bidirectional_cards(deck,
        "Why are control conditions important in TMS studies?",
        "To make causal inferences; need 'sham' pulse or stimulate 'control' brain area",
        ['neuromodulation', 'TMS']
    )
    
    # tDCS - SEPARATE from tACS
    create_bidirectional_cards(deck,
        "What is tDCS (Transcranial Direct Current Stimulation)?",
        "Low constant electrical currents sent between two electrodes on the scalp (anode and cathode)",
        ['neuromodulation', 'tDCS']
    )
    
    create_bidirectional_cards(deck,
        "What type of electrical current does tDCS use?",
        "Constant electrical currents (direct current)",
        ['neuromodulation', 'tDCS']
    )
    
    # tACS - SEPARATE from tDCS
    create_bidirectional_cards(deck,
        "What is tACS (Transcranial Alternating Current Stimulation)?",
        "Low oscillatory electrical currents sent between two electrodes on the scalp (anode and cathode)",
        ['neuromodulation', 'tACS']
    )
    
    create_bidirectional_cards(deck,
        "What type of electrical current does tACS use?",
        "Oscillatory electrical currents (alternating current)",
        ['neuromodulation', 'tACS']
    )
    
    create_bidirectional_cards(deck,
        "What can tACS do that tDCS cannot?",
        "tACS can induce oscillations at specific frequencies linked to cognitive processes",
        ['neuromodulation', 'tACS', 'tDCS']
    )
    
    # Shared properties of tDCS and tACS
    create_bidirectional_cards(deck,
        "What is the temporal resolution of tDCS and tACS?",
        "High temporal resolution (milliseconds)",
        ['neuromodulation', 'tDCS', 'tACS']
    )
    
    create_bidirectional_cards(deck,
        "What is the spatial resolution of tDCS and tACS?",
        "Low spatial resolution (many centimeters)",
        ['neuromodulation', 'tDCS', 'tACS']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of tDCS and tACS?",
        "• High temporal resolution (milliseconds)<br>• Can be used repeatedly",
        ['neuromodulation', 'tDCS', 'tACS']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of tDCS and tACS?",
        "• Low spatial resolution (many centimeters)<br>• Neural effects are not very clear/debated",
        ['neuromodulation', 'tDCS', 'tACS']
    )
    
    # tFUS
    create_bidirectional_cards(deck,
        "What is tFUS (Transcranial Focused Ultrasound)?",
        "Modulates excitability of neurons through acoustic pulses",
        ['neuromodulation', 'tFUS']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of tFUS?",
        "• High temporal resolution (milliseconds)<br>• High spatial resolution (order of millimeters)<br>• Can target deep brain structures",
        ['neuromodulation', 'tFUS']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of tFUS?",
        "• Relatively new technique, many unknowns<br>• May heat up the brain",
        ['neuromodulation', 'tFUS']
    )
    
    # DBS
    create_bidirectional_cards(deck,
        "What is DBS (Deep Brain Stimulation)?",
        "Surgical implant of a microelectrode directly in the brain that delivers electrical stimulation to target site (neurostimulator can be turned off with remote)",
        ['neuromodulation', 'DBS']
    )
    
    create_bidirectional_cards(deck,
        "What condition is DBS primarily used to treat?",
        "Parkinson's disease (stimulate subthalamic nucleus in basal ganglia)",
        ['neuromodulation', 'DBS', 'clinical']
    )
    
    # Computational Neuroscience
    create_bidirectional_cards(deck,
        "What are computational models useful for in neuroscience?",
        "• Summarizing measurements<br>• Explaining measurements<br>• Predicting measurements or generating new predictions for unseen conditions",
        ['computational']
    )
    
    create_bidirectional_cards(deck,
        "What are theory-driven models?",
        "Simulate brain processes grounded by theory and knowledge about biology",
        ['computational', 'models']
    )
    
    create_bidirectional_cards(deck,
        "What are data-driven models?",
        "Identify patterns in data or predict outcomes (theory 'agnostic')",
        ['computational', 'models']
    )
    
    create_bidirectional_cards(deck,
        "What are functional models?",
        "Characterize computations (transformations) between input and outputs; only aims to match outputs given inputs, components can be more abstract",
        ['computational', 'models']
    )
    
    create_bidirectional_cards(deck,
        "What are mechanistic models?",
        "Characterize details of a mechanism (e.g., biophysical or circuit); parallel actual physical components",
        ['computational', 'models']
    )
    
    create_bidirectional_cards(deck,
        "What makes a good computational model?",
        "• Accuracy (how well it performs in matching the system/predicting data)<br>• Understanding of model components and outcomes<br>• Understanding why model makes predictions and what causes it to fail",
        ['computational']
    )
    
    create_bidirectional_cards(deck,
        "What are the advantages of computational neuroscience?",
        "• Cheap (to certain extent)<br>• Non-invasive<br>• Provides insights into how and why questions<br>• Provides new testable hypotheses",
        ['computational']
    )
    
    create_bidirectional_cards(deck,
        "What are the disadvantages of computational neuroscience?",
        "• Large models quickly become hard to understand<br>• Devil is in the details (e.g., how you train and test models)",
        ['computational']
    )
    
    print(f"Generated {len(deck.notes)} cards so far...")
    
    # ===== SENSATION & PERCEPTION =====
    
    create_bidirectional_cards(deck,
        "What is sensation?",
        "The way our sensory organs receive information from the environment (the stimulus)",
        ['sensation-perception', 'definitions']
    )
    
    create_bidirectional_cards(deck,
        "What is transduction?",
        "Converting physical stimulus (such as light or sound) into neural activity",
        ['sensation-perception', 'definitions']
    )
    
    create_bidirectional_cards(deck,
        "What is perception?",
        "The mental process of becoming aware of, understanding, and/or recognizing the stimulus (doesn't have to be conscious experience)",
        ['sensation-perception', 'definitions']
    )
    
    create_bidirectional_cards(deck,
        "What is representation in neuroscience?",
        "How a neural state or activity correlates with, relates to, or is connected to a stimulus feature or event",
        ['sensation-perception', 'definitions']
    )
    
    # Visual System - Retina
    create_bidirectional_cards(deck,
        "What are midget ganglion cells (P-cells)?",
        "Small retinal ganglion cells with relatively slow neural signals; 80% of ganglion cells",
        ['visual-system', 'retina', 'midget']
    )
    
    create_bidirectional_cards(deck,
        "What input do midget ganglion cells receive?",
        "Get their input from cones (sensitive to color)",
        ['visual-system', 'retina', 'midget']
    )
    
    create_bidirectional_cards(deck,
        "What frequencies are midget cells sensitive to?",
        "• Sensitive to low (but not high) temporal frequencies<br>• Sensitive to high spatial frequencies",
        ['visual-system', 'retina', 'midget']
    )
    
    create_bidirectional_cards(deck,
        "Where do midget ganglion cells project?",
        "Project to parvocellular layers in LGN",
        ['visual-system', 'retina', 'midget']
    )
    
    create_bidirectional_cards(deck,
        "What are parasol ganglion cells (M-cells)?",
        "Large retinal ganglion cells with relatively fast neural signals",
        ['visual-system', 'retina', 'parasol']
    )
    
    create_bidirectional_cards(deck,
        "What input do parasol ganglion cells receive?",
        "Get their input from cones and rods (despite getting information from cones, they don't care about color)",
        ['visual-system', 'retina', 'parasol']
    )
    
    create_bidirectional_cards(deck,
        "What frequencies are parasol cells sensitive to?",
        "• Sensitive to medium and high temporal frequencies<br>• Sensitive to low spatial frequencies only",
        ['visual-system', 'retina', 'parasol']
    )
    
    create_bidirectional_cards(deck,
        "Where do parasol ganglion cells project?",
        "Project to magnocellular layers in LGN",
        ['visual-system', 'retina', 'parasol']
    )
    
    # LGN
    create_bidirectional_cards(deck,
        "What percentage of retinal axons terminate in the LGN?",
        "90% (10% terminates in subcortex, including Superior Colliculus and pulvinar nucleus)",
        ['visual-system', 'LGN']
    )
    
    create_bidirectional_cards(deck,
        "How many layers does the LGN have?",
        "Six layers: 2 ventral magnocellular, 4 dorsal parvocellular, plus interlaminar koniocellular layers",
        ['visual-system', 'LGN']
    )
    
    create_bidirectional_cards(deck,
        "What percentage of the LGN neural mass represents the fovea and immediate surround?",
        "50%",
        ['visual-system', 'LGN']
    )
    
    create_bidirectional_cards(deck,
        "What percentage of presynaptic connections onto LGN relay come from the retina?",
        "Only 10-20% (suggesting top-down control of visual processing)",
        ['visual-system', 'LGN']
    )
    
    create_bidirectional_cards(deck,
        "Describe parvocellular LGN pathway characteristics",
        "• Four dorsal layers receive midget retinal ganglion cell projections<br>• Small receptive fields<br>• Sustained response<br>• Slower conduction<br>• Input from 1-2 cone types<br>• Color and feature sensitivity",
        ['visual-system', 'LGN', 'parvocellular']
    )
    
    create_bidirectional_cards(deck,
        "Describe magnocellular LGN pathway characteristics",
        "• Two ventral layers receive parasol retinal ganglion cell projections<br>• Large receptive fields<br>• Transient response<br>• Rapidly conducting axons<br>• 3 cone types converge<br>• Motion sensitivity",
        ['visual-system', 'LGN', 'magnocellular']
    )
    
    create_bidirectional_cards(deck,
        "What is the parvocellular (P) pathway essential for?",
        "• Color vision<br>• High spatial frequency sensitivity (fine form discrimination)<br>• Low temporal frequency sensitivity (slow change)",
        ['visual-system', 'pathways', 'parvocellular']
    )
    
    create_bidirectional_cards(deck,
        "What is the magnocellular (M) pathway essential for?",
        "• Lower spatial frequency<br>• Higher temporal frequency",
        ['visual-system', 'pathways', 'magnocellular']
    )
    
    create_bidirectional_cards(deck,
        "According to Livingstone and Hubel (1988), how do primary visual pathways differ?",
        "Four ways: 1. Color, 2. Acuity (size of receptive field centers, spatial sensitivity), 3. Speed (temporal sensitivity), 4. Contrast (sensitivity to changes in brightness)",
        ['visual-system', 'pathways']
    )
    
    # V1
    create_bidirectional_cards(deck,
        "What is another name for primary visual cortex (V1)?",
        "Striate cortex (due to prominent stripe of white matter in layer 4, stria of Gennari)",
        ['visual-system', 'V1']
    )
    
    create_bidirectional_cards(deck,
        "What is cortical magnification?",
        "The fovea (center of gaze) - a small region of the visual field - is processed by a large number of neurons in visual cortex, especially compared to peripheral locations",
        ['visual-system', 'V1']
    )
    
    create_bidirectional_cards(deck,
        "How are edge detectors (simple cells) created in V1?",
        "V1 combines retinal ganglion cells (with on-center/off-surround or off-center/on-surround organization) into elongated on-off receptive fields",
        ['visual-system', 'V1']
    )
    
    create_bidirectional_cards(deck,
        "What are the three major vertically-oriented systems in V1?",
        "1. Orientation columns (neurons with selectivity for light bars with specific orientations)<br>2. Blobs (neurons in upper layers concerned with color)<br>3. Ocular dominance columns (neurons receiving inputs from left or right eye)",
        ['visual-system', 'V1']
    )
    
    create_bidirectional_cards(deck,
        "How does V1 elaborate elemental visual information?",
        "Two ways: 1. Edge detectors - each part of visual field represented by short line segments in all orientations (critical for form discrimination), 2. Binocular integration - input from both eyes combined (necessary for depth perception)",
        ['visual-system', 'V1']
    )
    
    # Visual Streams
    create_bidirectional_cards(deck,
        "What are the three visual processing streams in humans?",
        "1. Ventral (temporal) pathway - WHAT<br>2. Dorsal (parietal) pathway - WHERE/HOW<br>3. Lateral pathway - SOCIAL/ACTION",
        ['visual-system', 'streams']
    )
    
    create_bidirectional_cards(deck,
        "What is the ventral stream specialized for?",
        "Object recognition: color, texture, shape, object category and semantic association",
        ['visual-system', 'streams', 'ventral']
    )
    
    create_bidirectional_cards(deck,
        "What is the dorsal stream specialized for?",
        "Spatial perception: navigation, spatial awareness, visually guided action, object manipulation; motion and depth",
        ['visual-system', 'streams', 'dorsal']
    )
    
    create_bidirectional_cards(deck,
        "What is the lateral stream specialized for?",
        "Object action and dynamics: concept of action, object motion & interaction, body motion & interaction, haptics, verbs/language",
        ['visual-system', 'streams', 'lateral']
    )
    
    create_bidirectional_cards(deck,
        "Describe the What & Where hypothesis (Ungerleider & Mishkin, 1982)",
        "Appreciation of an object's qualities depends on IT cortex (ventral); spatial location depends on posterior parietal cortex (dorsal); emphasis on vision's primary role in perception",
        ['visual-system', 'streams', 'theory']
    )
    
    create_bidirectional_cards(deck,
        "Describe the Vision in Action hypothesis (Goodale & Milner, 1996)",
        "Ventral systems encode 'world out there' for perception (enduring characteristics); dorsal systems act upon that world for action (moment-to-moment changes, egocentric features); emphasis on output rather than input",
        ['visual-system', 'streams', 'theory']
    )
    
    # Dorsal Stream Details
    create_bidirectional_cards(deck,
        "What are MT cells specialized for?",
        "Primarily direction sensitive; large receptive fields (10x wider than in striate cortex)",
        ['visual-system', 'dorsal', 'MT']
    )
    
    create_bidirectional_cards(deck,
        "What do MT cells respond to?",
        "Motion as detected by contrasts in luminance, texture or color (crossover from parvocellular specialization)",
        ['visual-system', 'dorsal', 'MT']
    )
    
    create_bidirectional_cards(deck,
        "What is MST specialized for?",
        "Optic flow (locomotion through space) and biological motion",
        ['visual-system', 'dorsal', 'MST']
    )
    
    create_bidirectional_cards(deck,
        "What is akinetopsia?",
        "Scotomas for motion perception; lesions produce inability to see continuous motion (patients see snapshots - frozen objects in one position then jump to another)",
        ['visual-system', 'disorders', 'akinetopsia']
    )
    
    create_bidirectional_cards(deck,
        "What brain damage causes akinetopsia?",
        "Lesions in bilateral temporoparietal cortex (hMT+/V5)",
        ['visual-system', 'disorders', 'akinetopsia']
    )
    
    # Ventral Stream Details
    create_bidirectional_cards(deck,
        "Describe characteristics of IT (inferotemporal) area cells",
        "• Large receptive fields covering large part of visual field (related to object constancy)<br>• Locations biased to fovea<br>• Retinotopic organization (less tight than early visual areas)<br>• Responsive to particular stimulus categories (faces, hands, etc.)",
        ['visual-system', 'ventral', 'IT']
    )
    
    create_bidirectional_cards(deck,
        "What could Patient D.F. do and not do?",
        "COULD NOT: recognize or describe object features<br>COULD: use size and orientation of objects to control movements (bilateral damage to cortex ventral stream due to monoxide intoxication)",
        ['visual-system', 'lesions', 'patient-DF']
    )
    
    # Visual Agnosias
    create_bidirectional_cards(deck,
        "What is visual agnosia?",
        "Impairment of object recognition not attributable to loss of general intellectual ability or impairment in elementary visual perceptual processes; results from damage to secondary visual areas (usually ventral stream)",
        ['disorders', 'agnosia']
    )
    
    create_bidirectional_cards(deck,
        "What is apperceptive agnosia?",
        "Inability to develop a percept of the object; can describe simple features (brightness, color, line orientation) but cannot collate them to recognize, copy or match simple shapes; cannot draw/copy viewed objects (but can draw from memory)",
        ['disorders', 'agnosia', 'apperceptive']
    )
    
    create_bidirectional_cards(deck,
        "What brain damage causes apperceptive agnosia?",
        "Associated with bilateral damage to lateral occipital lobes",
        ['disorders', 'agnosia', 'apperceptive']
    )
    
    create_bidirectional_cards(deck,
        "What is integrative agnosia?",
        "Can see parts of object; can copy simple shapes in drawings; unable to integrate parts into whole (e.g., recognize walls and doors but not house); issues more pronounced when objects overlap",
        ['disorders', 'agnosia', 'integrative']
    )
    
    create_bidirectional_cards(deck,
        "What brain damage causes integrative agnosia?",
        "Associated with damage in medial ventral stream",
        ['disorders', 'agnosia', 'integrative']
    )
    
    create_bidirectional_cards(deck,
        "What is associative agnosia?",
        "Inability to recognize object despite normal and complete percept of object; can copy objects; can match similar looking objects; can define what object is from label (not a language or memory problem)",
        ['disorders', 'agnosia', 'associative']
    )
    
    create_bidirectional_cards(deck,
        "What brain damage causes associative agnosia?",
        "Associated with damage in anterior portion of ventral stream (anterior temporal cortex)",
        ['disorders', 'agnosia', 'associative']
    )
    
    create_bidirectional_cards(deck,
        "What is achromatopsia?",
        "Deficits in color perception from damage to ventral occipital cortex (hV4 and VO); almost always accompanied by other visual agnosia",
        ['disorders', 'agnosia', 'achromatopsia']
    )
    
    create_bidirectional_cards(deck,
        "What is prosopagnosia?",
        "Inability to recognize upright faces (even previously known faces, including own face in mirror); can recognize people by specific face information (mole, mustache); can recognize facial expressions normally; can distinguish human and non-human faces; can recognize other objects",
        ['disorders', 'agnosia', 'prosopagnosia']
    )
    
    create_bidirectional_cards(deck,
        "What brain damage causes prosopagnosia?",
        "Bilateral occipital-temporal junction; lateral mid-fusiform gyrus (right > left)",
        ['disorders', 'agnosia', 'prosopagnosia']
    )
    
    create_bidirectional_cards(deck,
        "What is the Fusiform Face Area (FFA)?",
        "Region in right lateral mid-fusiform gyrus activated by face perception; implies region specialized for perceiving and recognizing faces (Kanwisher et al., 1997)",
        ['visual-system', 'faces', 'FFA']
    )
    
    create_bidirectional_cards(deck,
        "What is alexia?",
        "Inability to read; can read letters but cannot form lexical representations; damage to left fusiform and lingual gyri (includes BA 18 and/or 19)",
        ['disorders', 'agnosia', 'alexia']
    )
    
    create_bidirectional_cards(deck,
        "What did Patient CK demonstrate about face vs object processing?",
        "Normal face recognition (upright faces only); integrative object agnosia; severe impairment in inverted faces; conclusion: face recognition depends on two systems (face-specific holistic system and part-based object-recognition system)",
        ['disorders', 'faces', 'patient-CK']
    )
    
    print(f"Generated {len(deck.notes)} cards so far...")
    
    # ===== ATTENTION =====
    
    create_bidirectional_cards(deck,
        "What is attention?",
        "Process by which some stimuli are selected for privileged processing",
        ['attention', 'definition']
    )
    
    create_bidirectional_cards(deck,
        "Why is attention necessary?",
        "Nervous system has limited capacity and cannot process all things at all times; stimuli compete for limited resources",
        ['attention', 'definition']
    )
    
    create_bidirectional_cards(deck,
        "What dual nature does attention have?",
        "Attention is both a PROCESS (orienting/selecting/gating) and a RESOURCE (capacity)",
        ['attention', 'definition']
    )
    
    # Components of Attention
    create_bidirectional_cards(deck,
        "What is arousal?",
        "A generalized sense of alertness",
        ['attention', 'components', 'arousal']
    )
    
    create_bidirectional_cards(deck,
        "What is sustained attention?",
        "Duration of focus; vigilance",
        ['attention', 'components', 'sustained']
    )
    
    create_bidirectional_cards(deck,
        "What is selective attention?",
        "Prioritization of information among competing representations",
        ['attention', 'components', 'selective']
    )
    
    create_bidirectional_cards(deck,
        "What is divided attention?",
        "Allocation of resources between different tasks",
        ['attention', 'components', 'divided']
    )
    
    # Types of Selective Attention
    create_bidirectional_cards(deck,
        "What are the three types of selective attention?",
        "1. Spatial (e.g., lower left or upper right of visual field)<br>2. Feature-based (e.g., specific orientation or color)<br>3. Object-based (e.g., friend's face in airport)",
        ['attention', 'selective', 'types']
    )
    
    create_bidirectional_cards(deck,
        "What is voluntary/endogenous/goal-directed attention?",
        "Relatively slow to deploy (at least 300 ms); sustained",
        ['attention', 'types', 'endogenous']
    )
    
    create_bidirectional_cards(deck,
        "What is reflexive/exogenous/stimulus-driven attention?",
        "Quick to deploy (50-150 ms); short-lived",
        ['attention', 'types', 'exogenous']
    )
    
    create_bidirectional_cards(deck,
        "What is overt attention?",
        "Attention with eye movements",
        ['attention', 'types', 'overt']
    )
    
    create_bidirectional_cards(deck,
        "What is covert attention?",
        "Attention without eye movements",
        ['attention', 'types', 'covert']
    )
    
    # Working Model of Attention
    create_bidirectional_cards(deck,
        "What are the three primary components in the working model of attention?",
        "1. Alertness (maintaining focus over time, top-down modulation)<br>2. (Re)Orienting (directing and re-directing attention, disengage and shift)<br>3. Executive (supervisory control, mediating/monitoring top-down and bottom-up)",
        ['attention', 'model']
    )
    
    # Brain Areas - RAS
    create_bidirectional_cards(deck,
        "What is the role of the Reticular Activating System (RAS) in attention?",
        "Major supportive role for attentional processing; general state of alertness needed for attentional functions; also plays role in phasic alertness when general arousal level is heightened temporarily in response to stimuli",
        ['attention', 'brain', 'RAS']
    )
    
    create_bidirectional_cards(deck,
        "What happens with a lesion to the Reticular Activating System?",
        "Leads to coma (0 arousal)",
        ['attention', 'brain', 'RAS']
    )
    
    create_bidirectional_cards(deck,
        "Does arousal equal attention?",
        "No - there can be attentional deficits in perfectly awake individuals; extreme arousal (as in pain or terror) may impair flexibility of attention",
        ['attention', 'arousal']
    )
    
    # Brain Areas - Superior Colliculus
    create_bidirectional_cards(deck,
        "What does the Superior Colliculus (SC) control?",
        "Ability to visually fixate on or foveate a stimulus; saccadic eye movements",
        ['attention', 'brain', 'SC']
    )
    
    # Brain Areas - Thalamus
    create_bidirectional_cards(deck,
        "What is the role of the thalamus in attention?",
        "• Medial dorsal, reticular & intralaminar nuclei: arousal and vigilance<br>• Pulvinar nucleus: sensory gating (selective attention)",
        ['attention', 'brain', 'thalamus']
    )
    
    create_bidirectional_cards(deck,
        "What happens with damage to the thalamus?",
        "Poor sensory gating (cannot selectively attend)",
        ['attention', 'brain', 'thalamus']
    )
    
    # Brain Areas - Parietal Lobe
    create_bidirectional_cards(deck,
        "What is the parietal lobe's role in attention?",
        "• Binding stimulus attributes (what + where information)<br>• Visuospatial aspects of attention<br>• Overall attentional allocation<br>• SPL involved in shifts of spatial attention<br>• IPL/TPJ damage causes spatial neglect<br>• Awareness of perceptual information",
        ['attention', 'brain', 'parietal']
    )
    
    # Brain Areas - Frontal Lobes
    create_bidirectional_cards(deck,
        "What is the frontal lobe's role in attention?",
        "High-level executive control of attention, including dividing attention between two tasks",
        ['attention', 'brain', 'frontal']
    )
    
    # Effects of Attention on Neural Activity
    create_bidirectional_cards(deck,
        "How does visual attention affect neural activity?",
        "• Attention enhances neural activity in functionally-relevant neurons (for attended vs unattended locations/features/objects)<br>• Attention influences synchronization of neural activity<br>• Increased synchronization between pulvinar and cortex<br>• Visual cortex: Increased spiking → reduced EEG oscillatory power in 8-15 Hz (alpha band)",
        ['attention', 'effects']
    )
    
    # Neglect
    create_bidirectional_cards(deck,
        "What is hemispatial neglect?",
        "Failure to perform on the side of space opposite the lesion; cannot be accounted for by visual, sensory, or motor deficit",
        ['attention', 'disorders', 'neglect']
    )
    
    create_bidirectional_cards(deck,
        "What other names is neglect known by?",
        "Hemineglect, hemispatial neglect, hemi-inattention, behavioural inattention, unilateral spatial neglect",
        ['attention', 'disorders', 'neglect']
    )
    
    create_bidirectional_cards(deck,
        "What brain damage typically causes left neglect?",
        "Damage to inferior parietal or superior temporal lobe (temporoparietal junction) or ventral frontal cortex of RIGHT hemisphere",
        ['attention', 'disorders', 'neglect']
    )
    
    create_bidirectional_cards(deck,
        "What is the difference between neglect and hemianopia?",
        "Hemianopia: blindness in one hemifield due to geniculocalcarine tract damage (turning head places object in working visual field)<br>Neglect: ignore left side of space (unawareness of left side of space); not compensated by head turning",
        ['attention', 'disorders', 'neglect']
    )
    
    create_bidirectional_cards(deck,
        "What are the two types of neglect?",
        "1. Spatial neglect (body-centered)<br>2. Object-centered neglect",
        ['attention', 'disorders', 'neglect']
    )
    
    create_bidirectional_cards(deck,
        "Can neglected stimuli still influence future behavior?",
        "Yes - evidence that neglected stimuli can still influence future behavior even though person was not consciously aware of stimulus (burning house experiment by Marshall and Halligan 1988; priming experiments)",
        ['attention', 'disorders', 'neglect']
    )
    
    # Theories of Neglect
    create_bidirectional_cards(deck,
        "What are the two competing theories of neglect?",
        "1. Attentional (3 hypotheses: inattention/unawareness, ipsilesional attention bias, inability to disengage)<br>2. Representational (failure to construct complete mental representation of contralesional space)",
        ['attention', 'disorders', 'neglect', 'theories']
    )
    
    create_bidirectional_cards(deck,
        "Describe the unawareness/inattention hypothesis of neglect",
        "Failure to act in left hemispace due to unawareness/inattention to the left; attention can be drawn leftward by enhancing motivation, adding salient/emotional information, increasing structure of stimulus array, or caloric stimulation",
        ['attention', 'disorders', 'neglect', 'theories']
    )
    
    create_bidirectional_cards(deck,
        "Describe the attention-bias hypothesis of neglect (Heilman & Mesulam)",
        "RH dominant for arousal and spatial attention; RH damage diminishes arousal/cognitive capacity, renders RH hypoactive; attentional bias produced by left hemisphere; RH capable of directing attention to both hemispaces, LH directs only to contralateral space (LH damage produces neglect of lesser severity)",
        ['attention', 'disorders', 'neglect', 'theories']
    )
    
    create_bidirectional_cards(deck,
        "Describe the inability to disengage hypothesis of neglect (Posner)",
        "Neglect may be disorder of orienting: failure to disengage attention from right-sided stimuli before shifting to left-sided stimuli; invalid cues indicating target to occur ipsilesionally resulted in much prolonged response time to contralesional stimuli",
        ['attention', 'disorders', 'neglect', 'theories']
    )
    
    create_bidirectional_cards(deck,
        "What is extinction in the context of neglect?",
        "Often observed with recovery from neglect; aware of left-sided stimuli, but 'extinguish' awareness when right-sided stimuli are presented simultaneously (bilateral simultaneous stimulation); can be visual, auditory, tactile",
        ['attention', 'disorders', 'neglect', 'extinction']
    )
    
    create_bidirectional_cards(deck,
        "What evidence supports the representational deficit theory of neglect?",
        "Not only stimulus-driven: hallucinations show same bias for left side; Bisiach & Luzzati (1978): Milanese patients described view in Piazza del Duomo toward and from cathedral with left-side omissions in both directions",
        ['attention', 'disorders', 'neglect', 'theories']
    )
    
    create_bidirectional_cards(deck,
        "What is the typical recovery course for neglect?",
        "Generally good recovery in weeks following injury; but recovery often partial: simultagnosia and/or extinction remain",
        ['attention', 'disorders', 'neglect', 'recovery']
    )
    
    # Balint's Syndrome
    create_bidirectional_cards(deck,
        "What are the three main symptoms of Balint's syndrome?",
        "1. Simultagnosia (inability to perceive visual field as whole)<br>2. Ocular apraxia (inability to make voluntary eye movements)<br>3. Optic ataxia (inability to make visually guided hand movements)",
        ['attention', 'disorders', 'Balint']
    )
    
    create_bidirectional_cards(deck,
        "What is simultagnosia?",
        "Inability to perceive visual field as a whole; when multiple objects are presented, patients can only perceive one at a time",
        ['attention', 'disorders', 'Balint', 'simultagnosia']
    )
    
    create_bidirectional_cards(deck,
        "What is ocular apraxia?",
        "Inability to make voluntary eye movements (to scan visual field or orient to object)",
        ['attention', 'disorders', 'Balint', 'ocular-apraxia']
    )
    
    create_bidirectional_cards(deck,
        "What is optic ataxia?",
        "Inability to make visually guided hand movements",
        ['attention', 'disorders', 'Balint', 'optic-ataxia']
    )
    
    create_bidirectional_cards(deck,
        "What brain damage causes Balint's syndrome?",
        "Bilateral lesions in posterior parietal and occipital cortex",
        ['attention', 'disorders', 'Balint']
    )
    
    create_bidirectional_cards(deck,
        "How is Balint's syndrome different from neglect syndrome?",
        "Neglect: unilateral cortical lesions (or subcortical areas)<br>Balint's: bilateral cortical lesions<br>Different perceptual deficits",
        ['attention', 'disorders', 'Balint', 'neglect']
    )
    
    # Shuffle and save
    random.shuffle(deck.notes)
    
    output_path = OUTPUT_DIR / 'PSYC3250M_Midterm_Anki_Deck.apkg'
    genanki.Package(deck).write_to_file(str(output_path))
    
    print(f"\n✓ Created Anki deck with {len(deck.notes)} cards")
    print(f"✓ Cards are bidirectional and shuffled")
    print(f"✓ Saved to: {output_path}")
    print(f"\nTo use:")
    print(f"1. Open Anki")
    print(f"2. File → Import")
    print(f"3. Select: {output_path.name}")
    print(f"\nGood luck on your midterm!")

if __name__ == '__main__':
    main()
