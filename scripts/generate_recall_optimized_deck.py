"""
PSYC 3250M Midterm Anki Deck Generator - RECALL OPTIMIZED
Questions designed for effective self-testing and long-term retention
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

ANKI_MODEL = genanki.Model(
    1607392320,  # New ID for updated model
    'PSYC 3250M Recall Model',
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
    """
)

def add_card(deck, question, answer, tags=[]):
    """Add single card (not bidirectional - only when it makes sense)"""
    note = genanki.Note(
        model=ANKI_MODEL,
        fields=[question, answer],
        tags=tags
    )
    deck.add_note(note)

def add_bidirectional(deck, question, answer, tags=[]):
    """Add bidirectional cards when appropriate for recall"""
    add_card(deck, question, answer, tags)
    add_card(deck, answer, question, tags + ['reverse'])

def main():
    deck = genanki.Deck(
        random.randrange(1 << 30, 1 << 31),
        'PSYC 3250M Midterm - Recall Optimized'
    )
    
    print("Generating recall-optimized cards...")
    
    # ===== STRUCTURAL MRI =====
    
    add_card(deck,
        "What is the spatial resolution of structural MRI?",
        "0.3 to 3 mm³ (depending on magnetic field strength and pulse sequence)",
        ['MRI', 'structural']
    )
    
    add_card(deck,
        "Why can't some patients undergo MRI scans?",
        "They have metal in their bodies or electronic devices like pacemakers",
        ['MRI', 'contraindications']
    )
    
    add_card(deck,
        "Is structural MRI invasive?",
        "No, it is non-invasive",
        ['MRI']
    )
    
    # ===== DTI =====
    
    add_bidirectional(deck,
        "DTI (Diffusion Tensor Imaging)",
        "Measures direction of water diffusion to reveal white matter tracts",
        ['DTI']
    )
    
    add_card(deck,
        "Why can DTI reveal white matter tracts?",
        "Water diffusion is restricted in white matter bundles, creating directional patterns",
        ['DTI', 'mechanism']
    )
    
    add_card(deck,
        "How long does a DTI scan take per person?",
        "15-60 minutes",
        ['DTI', 'timing']
    )
    
    # ===== PET =====
    
    add_card(deck,
        "What is injected in PET scanning?",
        "Radioactive water containing fast-decaying tracer isotopes (e.g., oxygen-15)",
        ['PET', 'method']
    )
    
    add_card(deck,
        "What does PET measure after injection?",
        "Where radioactive material accumulates in the brain",
        ['PET', 'measurement']
    )
    
    add_card(deck,
        "What is the spatial resolution of PET?",
        "~5-10 mm³ (voxel size)",
        ['PET', 'resolution']
    )
    
    add_card(deck,
        "What is the temporal resolution of PET?",
        "Poor: ~1 minute at best",
        ['PET', 'resolution']
    )
    
    add_card(deck,
        "Why is PET temporal resolution limited?",
        "Limited by radioactive agent decay (minutes)",
        ['PET', 'limitations']
    )
    
    add_card(deck,
        "How long does one PET brain volume take to collect?",
        "~30 minutes",
        ['PET', 'timing']
    )
    
    # ===== fMRI - BOLD =====
    
    add_bidirectional(deck,
        "BOLD",
        "Blood Oxygen Level Dependent",
        ['fMRI', 'acronym']
    )
    
    add_card(deck,
        "What ratio does BOLD measure?",
        "Oxygenated to deoxygenated blood",
        ['fMRI', 'BOLD']
    )
    
    add_card(deck,
        "When neural activity increases, what happens to blood flow?",
        "Blood flow increases",
        ['fMRI', 'BOLD', 'mechanism']
    )
    
    add_card(deck,
        "When neural activity increases, what happens to blood oxygenation?",
        "Blood oxygenation increases",
        ['fMRI', 'BOLD', 'mechanism']
    )
    
    add_card(deck,
        "Which type of blood is magnetic: oxygenated or deoxygenated?",
        "Oxygenated blood is magnetic",
        ['fMRI', 'BOLD']
    )
    
    add_card(deck,
        "Which type of blood is paramagnetic: oxygenated or deoxygenated?",
        "Deoxygenated blood is paramagnetic",
        ['fMRI', 'BOLD']
    )
    
    add_card(deck,
        "Why does fMRI require a baseline condition?",
        "BOLD measures relative signal change (% signal change), not absolute values",
        ['fMRI', 'BOLD', 'design']
    )
    
    add_bidirectional(deck,
        "HRF",
        "Hemodynamic Response Function",
        ['fMRI', 'acronym']
    )
    
    add_card(deck,
        "What does the HRF show?",
        "Increase in BOLD signal in response to stimulus or neural activation",
        ['fMRI', 'HRF']
    )
    
    # ===== fMRI DESIGNS =====
    
    add_card(deck,
        "What is the main advantage of blocked fMRI designs?",
        "High detection power",
        ['fMRI', 'blocked']
    )
    
    add_card(deck,
        "What is blocked fMRI design robust to?",
        "Noise (e.g., differences in slice timing)",
        ['fMRI', 'blocked']
    )
    
    add_card(deck,
        "Why can't blocked designs examine individual trial effects?",
        "Cannot separate correct vs incorrect trials or remembered vs forgotten items",
        ['fMRI', 'blocked', 'limitation']
    )
    
    add_card(deck,
        "What assumption does blocked fMRI make about participants?",
        "Continuous engagement throughout the block",
        ['fMRI', 'blocked']
    )
    
    add_card(deck,
        "Can event-related fMRI designs create post-hoc conditions?",
        "Yes, based on participant behavior",
        ['fMRI', 'event-related']
    )
    
    add_card(deck,
        "How do event-related designs handle overlapping responses?",
        "Use statistical methods to separate overlapping fMRI responses of different trials",
        ['fMRI', 'event-related']
    )
    
    add_card(deck,
        "Do event-related designs have better or worse detection power than blocked?",
        "Reduced detection/power compared to blocked designs",
        ['fMRI', 'event-related', 'limitation']
    )
    
    add_card(deck,
        "What does event-related fMRI require for accurate detection?",
        "Accurate modeling of the HRF",
        ['fMRI', 'event-related']
    )
    
    add_card(deck,
        "Can the HRF differ across brain regions?",
        "Yes",
        ['fMRI', 'HRF']
    )
    
    # ===== fMRI ANALYSIS =====
    
    add_card(deck,
        "In univariate fMRI analysis, how many values per condition are considered?",
        "Only 1 value per condition (e.g., average signal of voxel or ROI)",
        ['fMRI', 'univariate']
    )
    
    add_card(deck,
        "What does univariate analysis contrast?",
        "BOLD response for different conditions in a voxel or ROI",
        ['fMRI', 'univariate']
    )
    
    add_card(deck,
        "What does multivariate fMRI analysis consider?",
        "Pattern of responses across multiple voxels per condition",
        ['fMRI', 'MVPA']
    )
    
    add_bidirectional(deck,
        "MVPA",
        "Multi-Voxel Pattern Analysis",
        ['fMRI', 'acronym']
    )
    
    add_card(deck,
        "What technique does MVPA use?",
        "Machine learning algorithms to predict (decode) how response patterns relate to conditions",
        ['fMRI', 'MVPA']
    )
    
    add_card(deck,
        "What does functional connectivity analysis correlate?",
        "BOLD time series of different voxels",
        ['fMRI', 'connectivity']
    )
    
    add_card(deck,
        "What is the purpose of functional connectivity analysis?",
        "Identify and characterize brain networks",
        ['fMRI', 'connectivity']
    )
    
    add_card(deck,
        "What type of brain activity does resting-state fMRI measure?",
        "Spontaneous or intrinsic brain activity",
        ['fMRI', 'resting-state']
    )
    
    add_card(deck,
        "What does fMRI measure: neurons directly or blood flow?",
        "Blood flow (indirect measure of brain activity)",
        ['fMRI', 'limitation']
    )
    
    add_card(deck,
        "Where does fMRI have signal dropout?",
        "At junctions between air and tissue (sinuses, ear canals)",
        ['fMRI', 'limitation']
    )
    
    add_card(deck,
        "What is the temporal resolution of fMRI?",
        "Relatively slow (seconds)",
        ['fMRI', 'resolution']
    )
    
    add_card(deck,
        "What is the spatial resolution of fMRI?",
        "Good (millimeters)",
        ['fMRI', 'resolution']
    )
    
    # ===== MRS =====
    
    add_bidirectional(deck,
        "MRS",
        "Magnetic Resonance Spectroscopy",
        ['MRS', 'acronym']
    )
    
    add_card(deck,
        "What does MRS measure?",
        "Chemical composition of brain tissue",
        ['MRS']
    )
    
    add_card(deck,
        "Name two neurochemicals measured by MRS",
        "GABA levels and glutamate levels",
        ['MRS', 'neurochemicals']
    )
    
    add_card(deck,
        "How long does one MRS measurement take?",
        "About 10 minutes for one large voxel",
        ['MRS', 'timing']
    )
    
    add_card(deck,
        "What is the spatial resolution of MRS?",
        "Low (multiple centimeters)",
        ['MRS', 'resolution']
    )
    
    add_card(deck,
        "What is MRS sometimes called?",
        "Virtual biopsy",
        ['MRS']
    )
    
    # ===== EEG =====
    
    add_bidirectional(deck,
        "EEG",
        "Electroencephalography",
        ['EEG', 'acronym']
    )
    
    add_card(deck,
        "What does EEG measure?",
        "Summed electrical activity from many neurons across the scalp",
        ['EEG']
    )
    
    add_card(deck,
        "What is EEG's temporal resolution?",
        "Millisecond time resolution (good)",
        ['EEG', 'resolution']
    )
    
    add_card(deck,
        "What is EEG's spatial resolution?",
        "Poor (~5-10 cm)",
        ['EEG', 'resolution']
    )
    
    add_card(deck,
        "Is EEG expensive?",
        "No, it's cheap",
        ['EEG', 'cost']
    )
    
    add_card(deck,
        "Is EEG invasive?",
        "No, non-invasive",
        ['EEG']
    )
    
    add_card(deck,
        "What makes EEG signals difficult to interpret?",
        "Difficult to disentangle different signals and their neural origin",
        ['EEG', 'limitation']
    )
    
    add_card(deck,
        "When neurons are active, what creates a dipole?",
        "Currents flowing in/out of the cell",
        ['EEG', 'mechanism']
    )
    
    # ===== MEG =====
    
    add_bidirectional(deck,
        "MEG",
        "Magnetoencephalography",
        ['MEG', 'acronym']
    )
    
    add_card(deck,
        "What does MEG measure?",
        "Summed tiny fluctuations in magnetic fields across the scalp",
        ['MEG']
    )
    
    add_card(deck,
        "Why does MEG have better spatial resolution than EEG?",
        "Magnetic signals are not affected by volume conduction (passive spread of electrical currents across tissues)",
        ['MEG', 'advantage']
    )
    
    add_card(deck,
        "What is MEG's spatial resolution?",
        "~4-8 cm (slightly better than EEG but still poor)",
        ['MEG', 'resolution']
    )
    
    add_card(deck,
        "What is MEG's temporal resolution?",
        "Milliseconds (good)",
        ['MEG', 'resolution']
    )
    
    add_card(deck,
        "What makes MEG setup easier than EEG?",
        "No gel or salt solution needed",
        ['MEG', 'advantage']
    )
    
    add_card(deck,
        "Is MEG expensive?",
        "Yes, expensive",
        ['MEG', 'cost']
    )
    
    # ===== ECoG/sEEG =====
    
    add_bidirectional(deck,
        "ECoG",
        "Electrocorticography",
        ['ECoG', 'acronym']
    )
    
    add_card(deck,
        "What makes ECoG different from EEG?",
        "Electrodes are placed directly on the cortex surface (invasive)",
        ['ECoG']
    )
    
    add_card(deck,
        "What is ECoG's temporal resolution?",
        "Sub-millisecond (very high)",
        ['ECoG', 'resolution']
    )
    
    add_card(deck,
        "Why is ECoG measurement noise low?",
        "Direct recording from brain surface",
        ['ECoG', 'advantage']
    )
    
    add_card(deck,
        "What is a major disadvantage of ECoG for research?",
        "No control over electrode placement and experiment time",
        ['ECoG', 'limitation']
    )
    
    add_card(deck,
        "Why might ECoG brain tissue not be representative?",
        "Brain tissue may be diseased or damaged",
        ['ECoG', 'limitation']
    )
    
    # ===== ERPs =====
    
    add_bidirectional(deck,
        "ERP",
        "Event-Related Potential",
        ['ERP', 'acronym']
    )
    
    add_card(deck,
        "How is an ERP created?",
        "Average electrical brain response over many trials",
        ['ERP', 'method']
    )
    
    add_card(deck,
        "What happens to non-phase-locked activity when averaging trials?",
        "It may be cancelled out",
        ['ERP', 'limitation']
    )
    
    add_card(deck,
        "What are asynchronous broadband (high gamma) responses?",
        "Increase in overall response across broad frequencies (not phase-locked or rhythmic)",
        ['ECoG', 'oscillations']
    )
    
    add_card(deck,
        "What do asynchronous broadband responses reflect?",
        "Integration of neural firing by dendrites",
        ['ECoG', 'oscillations']
    )
    
    add_card(deck,
        "Why are high gamma responses best observed in higher frequencies?",
        "Signals are not masked by synchronous responses",
        ['ECoG', 'oscillations']
    )
    
    # ===== TMS =====
    
    add_bidirectional(deck,
        "TMS",
        "Transcranial Magnetic Stimulation",
        ['TMS', 'acronym']
    )
    
    add_card(deck,
        "How does TMS work?",
        "Magnetic field outside skull induces electric field inside skull",
        ['TMS', 'mechanism']
    )
    
    add_card(deck,
        "What does TMS create?",
        "A 'virtual lesion' by disrupting normal brain activity",
        ['TMS', 'effect']
    )
    
    add_card(deck,
        "What is TMS's spatial resolution?",
        "Reasonable (1-2 centimeters)",
        ['TMS', 'resolution']
    )
    
    add_card(deck,
        "What is TMS's temporal resolution?",
        "Sub-millisecond (high)",
        ['TMS', 'resolution']
    )
    
    add_card(deck,
        "What type of information does TMS provide about brain areas?",
        "Causal role in particular functions",
        ['TMS', 'advantage']
    )
    
    add_card(deck,
        "What is a major anatomical limitation of TMS?",
        "Restricted to brain regions close to skull",
        ['TMS', 'limitation']
    )
    
    add_card(deck,
        "What is an uncomfortable side effect of TMS?",
        "Muscle twitches",
        ['TMS', 'limitation']
    )
    
    add_card(deck,
        "Why do TMS studies need control conditions?",
        "To make causal inferences (need sham pulse or control area stimulation)",
        ['TMS', 'design']
    )
    
    # ===== tDCS =====
    
    add_bidirectional(deck,
        "tDCS",
        "Transcranial Direct Current Stimulation",
        ['tDCS', 'acronym']
    )
    
    add_card(deck,
        "What type of current does tDCS use?",
        "Constant (direct) electrical currents",
        ['tDCS', 'mechanism']
    )
    
    add_card(deck,
        "Where are the electrodes placed in tDCS?",
        "On the scalp (anode and cathode)",
        ['tDCS']
    )
    
    add_card(deck,
        "What is tDCS's spatial resolution?",
        "Low (many centimeters)",
        ['tDCS', 'resolution']
    )
    
    add_card(deck,
        "What is tDCS's temporal resolution?",
        "High (milliseconds)",
        ['tDCS', 'resolution']
    )
    
    add_card(deck,
        "Is tDCS well-understood?",
        "No, neural effects are not very clear and debated",
        ['tDCS', 'limitation']
    )
    
    # ===== tACS =====
    
    add_bidirectional(deck,
        "tACS",
        "Transcranial Alternating Current Stimulation",
        ['tACS', 'acronym']
    )
    
    add_card(deck,
        "What type of current does tACS use?",
        "Oscillatory (alternating) electrical currents",
        ['tACS', 'mechanism']
    )
    
    add_card(deck,
        "What can tACS do that tDCS cannot?",
        "Induce oscillations at specific frequencies linked to cognitive processes",
        ['tACS', 'advantage']
    )
    
    add_card(deck,
        "What is tACS's spatial resolution?",
        "Low (many centimeters)",
        ['tACS', 'resolution']
    )
    
    add_card(deck,
        "What is tACS's temporal resolution?",
        "High (milliseconds)",
        ['tACS', 'resolution']
    )
    
    # ===== tFUS =====
    
    add_bidirectional(deck,
        "tFUS",
        "Transcranial Focused Ultrasound",
        ['tFUS', 'acronym']
    )
    
    add_card(deck,
        "How does tFUS modulate neurons?",
        "Through acoustic pulses",
        ['tFUS', 'mechanism']
    )
    
    add_card(deck,
        "What is tFUS's spatial resolution?",
        "High (order of millimeters)",
        ['tFUS', 'resolution']
    )
    
    add_card(deck,
        "What is tFUS's temporal resolution?",
        "High (milliseconds)",
        ['tFUS', 'resolution']
    )
    
    add_card(deck,
        "What can tFUS target that other methods cannot?",
        "Deep brain structures",
        ['tFUS', 'advantage']
    )
    
    add_card(deck,
        "Why is tFUS still uncertain as a technique?",
        "Relatively new with many unknowns; may heat up the brain",
        ['tFUS', 'limitation']
    )
    
    # ===== DBS =====
    
    add_bidirectional(deck,
        "DBS",
        "Deep Brain Stimulation",
        ['DBS', 'acronym']
    )
    
    add_card(deck,
        "Is DBS invasive?",
        "Yes, surgical implant of microelectrode directly in brain",
        ['DBS']
    )
    
    add_card(deck,
        "What does DBS stimulate to treat Parkinson's disease?",
        "Subthalamic nucleus in basal ganglia",
        ['DBS', 'clinical']
    )
    
    add_card(deck,
        "Can DBS be turned off?",
        "Yes, with a remote control",
        ['DBS']
    )
    
    # ===== COMPUTATIONAL NEUROSCIENCE =====
    
    add_card(deck,
        "What can computational models do for neuroscience? (name one)",
        "Summarize measurements, explain measurements, or predict measurements",
        ['computational']
    )
    
    add_card(deck,
        "What are theory-driven models grounded in?",
        "Theory and knowledge about biology",
        ['computational', 'models']
    )
    
    add_card(deck,
        "Are data-driven models theory-based?",
        "No, they are theory 'agnostic'",
        ['computational', 'models']
    )
    
    add_card(deck,
        "What do functional models aim to match?",
        "Outputs given inputs (components can be abstract)",
        ['computational', 'models']
    )
    
    add_card(deck,
        "What do mechanistic models parallel?",
        "Actual physical components (e.g., cellular currents)",
        ['computational', 'models']
    )
    
    add_card(deck,
        "Name one criterion for evaluating computational models",
        "Accuracy, understanding of components, or understanding of predictions/failures",
        ['computational']
    )
    
    add_card(deck,
        "Are computational models expensive to run?",
        "Relatively cheap (to certain extent)",
        ['computational', 'advantage']
    )
    
    add_card(deck,
        "What happens to large computational models?",
        "They quickly become hard to understand",
        ['computational', 'limitation']
    )
    
    print(f"Generated {len(deck.notes)} cards so far...")
    
    # ===== SENSATION & PERCEPTION =====
    
    add_card(deck,
        "What do sensory organs do in sensation?",
        "Receive information from the environment",
        ['sensation-perception']
    )
    
    add_bidirectional(deck,
        "Transduction",
        "Converting physical stimulus into neural activity",
        ['sensation-perception']
    )
    
    add_card(deck,
        "Does perception have to be conscious?",
        "No",
        ['sensation-perception']
    )
    
    add_card(deck,
        "What is perception?",
        "Mental process of becoming aware of, understanding, or recognizing a stimulus",
        ['sensation-perception']
    )
    
    # ===== RETINAL GANGLION CELLS =====
    
    add_card(deck,
        "What percentage of ganglion cells are midget cells?",
        "80%",
        ['visual-system', 'retina', 'midget']
    )
    
    add_card(deck,
        "Are midget cells large or small?",
        "Small",
        ['visual-system', 'retina', 'midget']
    )
    
    add_card(deck,
        "Are midget cell neural signals fast or slow?",
        "Relatively slow",
        ['visual-system', 'retina', 'midget']
    )
    
    add_card(deck,
        "What photoreceptors provide input to midget cells?",
        "Cones",
        ['visual-system', 'retina', 'midget']
    )
    
    add_card(deck,
        "Are midget cells color-sensitive?",
        "Yes",
        ['visual-system', 'retina', 'midget']
    )
    
    add_card(deck,
        "Are midget cells sensitive to high or low temporal frequencies?",
        "Low temporal frequencies (not high)",
        ['visual-system', 'retina', 'midget']
    )
    
    add_card(deck,
        "Are midget cells sensitive to high or low spatial frequencies?",
        "High spatial frequencies",
        ['visual-system', 'retina', 'midget']
    )
    
    add_card(deck,
        "Where do midget cells project in the LGN?",
        "Parvocellular layers",
        ['visual-system', 'retina', 'midget']
    )
    
    add_card(deck,
        "Are parasol cells large or small?",
        "Large",
        ['visual-system', 'retina', 'parasol']
    )
    
    add_card(deck,
        "Are parasol cell neural signals fast or slow?",
        "Relatively fast",
        ['visual-system', 'retina', 'parasol']
    )
    
    add_card(deck,
        "What photoreceptors provide input to parasol cells?",
        "Cones and rods",
        ['visual-system', 'retina', 'parasol']
    )
    
    add_card(deck,
        "Are parasol cells color-sensitive?",
        "No (despite getting input from cones)",
        ['visual-system', 'retina', 'parasol']
    )
    
    add_card(deck,
        "Are parasol cells sensitive to high or low temporal frequencies?",
        "Medium and high temporal frequencies",
        ['visual-system', 'retina', 'parasol']
    )
    
    add_card(deck,
        "Are parasol cells sensitive to high or low spatial frequencies?",
        "Low spatial frequencies only",
        ['visual-system', 'retina', 'parasol']
    )
    
    add_card(deck,
        "Where do parasol cells project in the LGN?",
        "Magnocellular layers",
        ['visual-system', 'retina', 'parasol']
    )
    
    # ===== LGN =====
    
    add_bidirectional(deck,
        "LGN",
        "Lateral Geniculate Nucleus",
        ['visual-system', 'acronym']
    )
    
    add_card(deck,
        "What percentage of retinal axons go to the LGN?",
        "90%",
        ['visual-system', 'LGN']
    )
    
    add_card(deck,
        "Where does the other 10% of retinal axons go?",
        "Subcortex (including Superior Colliculus and pulvinar nucleus)",
        ['visual-system', 'LGN']
    )
    
    add_card(deck,
        "How many magnocellular layers does the LGN have?",
        "2 ventral layers",
        ['visual-system', 'LGN']
    )
    
    add_card(deck,
        "How many parvocellular layers does the LGN have?",
        "4 dorsal layers",
        ['visual-system', 'LGN']
    )
    
    add_card(deck,
        "What percentage of LGN represents the fovea?",
        "50%",
        ['visual-system', 'LGN']
    )
    
    add_card(deck,
        "What percentage of LGN input comes from the retina?",
        "Only 10-20% (rest is top-down)",
        ['visual-system', 'LGN']
    )
    
    add_card(deck,
        "Do parvocellular neurons have large or small receptive fields?",
        "Small",
        ['visual-system', 'LGN', 'parvocellular']
    )
    
    add_card(deck,
        "Do parvocellular neurons have sustained or transient responses?",
        "Sustained",
        ['visual-system', 'LGN', 'parvocellular']
    )
    
    add_card(deck,
        "Are parvocellular axons fast or slow conducting?",
        "Slower conduction",
        ['visual-system', 'LGN', 'parvocellular']
    )
    
    add_card(deck,
        "How many cone types provide input to parvocellular neurons?",
        "1-2 cone types",
        ['visual-system', 'LGN', 'parvocellular']
    )
    
    add_card(deck,
        "Are parvocellular neurons sensitive to color or motion?",
        "Color and features",
        ['visual-system', 'LGN', 'parvocellular']
    )
    
    add_card(deck,
        "Do magnocellular neurons have large or small receptive fields?",
        "Large",
        ['visual-system', 'LGN', 'magnocellular']
    )
    
    add_card(deck,
        "Do magnocellular neurons have sustained or transient responses?",
        "Transient",
        ['visual-system', 'LGN', 'magnocellular']
    )
    
    add_card(deck,
        "Are magnocellular axons fast or slow conducting?",
        "Rapidly conducting",
        ['visual-system', 'LGN', 'magnocellular']
    )
    
    add_card(deck,
        "How many cone types converge on magnocellular neurons?",
        "3 cone types",
        ['visual-system', 'LGN', 'magnocellular']
    )
    
    add_card(deck,
        "Are magnocellular neurons sensitive to color or motion?",
        "Motion",
        ['visual-system', 'LGN', 'magnocellular']
    )
    
    # ===== PATHWAYS =====
    
    add_card(deck,
        "Is the parvocellular pathway essential for color vision?",
        "Yes",
        ['visual-system', 'parvocellular']
    )
    
    add_card(deck,
        "Is the parvocellular pathway sensitive to high or low spatial frequencies?",
        "High spatial frequencies (fine form discrimination)",
        ['visual-system', 'parvocellular']
    )
    
    add_card(deck,
        "Is the parvocellular pathway sensitive to high or low temporal frequencies?",
        "Low temporal frequencies (slow change)",
        ['visual-system', 'parvocellular']
    )
    
    add_card(deck,
        "Is the magnocellular pathway sensitive to high or low spatial frequencies?",
        "Lower spatial frequencies",
        ['visual-system', 'magnocellular']
    )
    
    add_card(deck,
        "Is the magnocellular pathway sensitive to high or low temporal frequencies?",
        "Higher temporal frequencies",
        ['visual-system', 'magnocellular']
    )
    
    add_card(deck,
        "According to Livingstone & Hubel (1988), what are the 4 ways M & P pathways differ?",
        "1. Color, 2. Acuity, 3. Speed, 4. Contrast",
        ['visual-system', 'pathways']
    )
    
    # ===== V1 =====
    
    add_card(deck,
        "What is another name for V1?",
        "Striate cortex",
        ['visual-system', 'V1']
    )
    
    add_card(deck,
        "Why is V1 called striate cortex?",
        "Prominent stripe of white matter in layer 4 (stria of Gennari)",
        ['visual-system', 'V1']
    )
    
    add_bidirectional(deck,
        "Cortical magnification",
        "Fovea processed by large number of neurons compared to periphery",
        ['visual-system', 'V1']
    )
    
    add_card(deck,
        "How does V1 create edge detectors?",
        "Combines retinal ganglion cells (center-surround) into elongated on-off receptive fields",
        ['visual-system', 'V1']
    )
    
    add_card(deck,
        "What are orientation columns in V1?",
        "Neurons selective for light bars with specific orientations",
        ['visual-system', 'V1']
    )
    
    add_card(deck,
        "What are blobs in V1?",
        "Neurons in upper layers concerned with color",
        ['visual-system', 'V1']
    )
    
    add_card(deck,
        "What are ocular dominance columns?",
        "Neurons receiving inputs from left or right eye",
        ['visual-system', 'V1']
    )
    
    add_card(deck,
        "What is one way V1 elaborates visual information?",
        "Edge detectors (represents visual field with line segments in all orientations for form discrimination)",
        ['visual-system', 'V1']
    )
    
    add_card(deck,
        "What is the second way V1 elaborates visual information?",
        "Binocular integration (combines input from both eyes for depth perception)",
        ['visual-system', 'V1']
    )
    
    # ===== VISUAL STREAMS =====
    
    add_card(deck,
        "What is the ventral stream for?",
        "WHAT - object recognition",
        ['visual-system', 'streams']
    )
    
    add_card(deck,
        "What is the dorsal stream for?",
        "WHERE/HOW - spatial perception and action",
        ['visual-system', 'streams']
    )
    
    add_card(deck,
        "What is the lateral stream for?",
        "SOCIAL/ACTION - object action and dynamics",
        ['visual-system', 'streams']
    )
    
    add_card(deck,
        "What does the ventral stream process?",
        "Color, texture, shape, object category, semantic association",
        ['visual-system', 'ventral']
    )
    
    add_card(deck,
        "What does the dorsal stream process?",
        "Navigation, spatial awareness, visually guided action, object manipulation, motion, depth",
        ['visual-system', 'dorsal']
    )
    
    add_card(deck,
        "What does Ungerleider & Mishkin's 'What & Where' hypothesis emphasize?",
        "Vision's primary role in perception",
        ['visual-system', 'theory']
    )
    
    add_card(deck,
        "What does Goodale & Milner's 'Vision in Action' hypothesis emphasize?",
        "Output of systems (perception vs action) rather than input",
        ['visual-system', 'theory']
    )
    
    add_card(deck,
        "According to Vision in Action, what does the ventral stream encode?",
        "World out there for perception (enduring characteristics)",
        ['visual-system', 'theory']
    )
    
    add_card(deck,
        "According to Vision in Action, what does the dorsal stream encode?",
        "Information for action (moment-to-moment changes, egocentric features)",
        ['visual-system', 'theory']
    )
    
    # ===== DORSAL STREAM DETAILS =====
    
    add_card(deck,
        "Are MT cell receptive fields large or small?",
        "Large (10x wider than striate cortex)",
        ['visual-system', 'MT']
    )
    
    add_card(deck,
        "What are MT cells primarily sensitive to?",
        "Direction (motion)",
        ['visual-system', 'MT']
    )
    
    add_card(deck,
        "Can MT cells respond to motion detected by color contrast?",
        "Yes (crossover from parvocellular)",
        ['visual-system', 'MT']
    )
    
    add_bidirectional(deck,
        "MST specialization",
        "Optic flow and biological motion",
        ['visual-system', 'MST']
    )
    
    add_bidirectional(deck,
        "Akinetopsia",
        "Scotomas for motion perception (see snapshots instead of continuous motion)",
        ['disorders', 'akinetopsia']
    )
    
    add_card(deck,
        "What brain damage causes akinetopsia?",
        "Bilateral temporoparietal cortex (hMT+/V5)",
        ['disorders', 'akinetopsia']
    )
    
    # ===== VENTRAL STREAM DETAILS =====
    
    add_card(deck,
        "Do IT area cells have large or small receptive fields?",
        "Large (cover large part of visual field)",
        ['visual-system', 'IT']
    )
    
    add_card(deck,
        "Where are IT cell receptive fields biased?",
        "Fovea",
        ['visual-system', 'IT']
    )
    
    add_card(deck,
        "What are IT cells responsive to?",
        "Particular stimulus categories (faces, hands, etc.)",
        ['visual-system', 'IT']
    )
    
    add_card(deck,
        "Is IT retinotopic organization tight or loose?",
        "Less tight than early visual areas",
        ['visual-system', 'IT']
    )
    
    add_card(deck,
        "What could Patient D.F. NOT do?",
        "Recognize or describe object features",
        ['lesions', 'patient-DF']
    )
    
    add_card(deck,
        "What COULD Patient D.F. do?",
        "Use size and orientation to control movements",
        ['lesions', 'patient-DF']
    )
    
    add_card(deck,
        "What caused Patient D.F.'s deficits?",
        "Bilateral ventral stream damage from monoxide intoxication",
        ['lesions', 'patient-DF']
    )
    
    # ===== AGNOSIAS =====
    
    add_bidirectional(deck,
        "Visual agnosia",
        "Impairment of object recognition not due to intellectual or elementary visual deficits",
        ['disorders', 'agnosia']
    )
    
    add_card(deck,
        "Where is damage in visual agnosia?",
        "Secondary visual areas (usually ventral stream)",
        ['disorders', 'agnosia']
    )
    
    add_card(deck,
        "What CAN apperceptive agnosia patients do?",
        "Describe simple features (brightness, color, orientation); draw from memory",
        ['disorders', 'apperceptive']
    )
    
    add_card(deck,
        "What CANNOT apperceptive agnosia patients do?",
        "Collate features to recognize, copy or match shapes; draw/copy viewed objects",
        ['disorders', 'apperceptive']
    )
    
    add_card(deck,
        "Where is damage in apperceptive agnosia?",
        "Bilateral lateral occipital lobes",
        ['disorders', 'apperceptive']
    )
    
    add_card(deck,
        "What CAN integrative agnosia patients do?",
        "See parts of objects; copy simple shapes",
        ['disorders', 'integrative']
    )
    
    add_card(deck,
        "What CANNOT integrative agnosia patients do?",
        "Integrate parts into whole (worse with overlapping objects)",
        ['disorders', 'integrative']
    )
    
    add_card(deck,
        "Where is damage in integrative agnosia?",
        "Medial ventral stream",
        ['disorders', 'integrative']
    )
    
    add_card(deck,
        "What CAN associative agnosia patients do?",
        "Copy objects; match similar objects; define object from label; perceive object completely",
        ['disorders', 'associative']
    )
    
    add_card(deck,
        "What CANNOT associative agnosia patients do?",
        "Recognize objects despite normal percept",
        ['disorders', 'associative']
    )
    
    add_card(deck,
        "Where is damage in associative agnosia?",
        "Anterior ventral stream (anterior temporal cortex)",
        ['disorders', 'associative']
    )
    
    add_bidirectional(deck,
        "Achromatopsia",
        "Deficits in color perception from ventral occipital cortex damage (hV4 and VO)",
        ['disorders', 'achromatopsia']
    )
    
    add_card(deck,
        "What CAN prosopagnosia patients recognize?",
        "Facial expressions; distinguish human vs non-human faces; other objects; people by specific features (mole, mustache)",
        ['disorders', 'prosopagnosia']
    )
    
    add_card(deck,
        "What CANNOT prosopagnosia patients recognize?",
        "Upright faces (even their own in a mirror)",
        ['disorders', 'prosopagnosia']
    )
    
    add_card(deck,
        "Where is damage in prosopagnosia?",
        "Bilateral occipital-temporal junction, lateral mid-fusiform gyrus (right > left)",
        ['disorders', 'prosopagnosia']
    )
    
    add_bidirectional(deck,
        "FFA",
        "Fusiform Face Area",
        ['visual-system', 'acronym']
    )
    
    add_card(deck,
        "Where is the FFA located?",
        "Right lateral mid-fusiform gyrus",
        ['visual-system', 'FFA']
    )
    
    add_card(deck,
        "What is the FFA specialized for?",
        "Perceiving and recognizing faces",
        ['visual-system', 'FFA']
    )
    
    add_bidirectional(deck,
        "Alexia",
        "Inability to read; can read letters but cannot form lexical representations",
        ['disorders', 'alexia']
    )
    
    add_card(deck,
        "Where is damage in alexia?",
        "Left fusiform and lingual gyri (BA 18 and/or 19)",
        ['disorders', 'alexia']
    )
    
    add_card(deck,
        "What did Patient CK show about face recognition?",
        "Depends on two systems: face-specific holistic AND part-based object-recognition",
        ['lesions', 'patient-CK']
    )
    
    print(f"Generated {len(deck.notes)} cards so far...")
    
    # ===== ATTENTION =====
    
    add_card(deck,
        "What is attention?",
        "Process by which some stimuli are selected for privileged processing",
        ['attention']
    )
    
    add_card(deck,
        "Is attention a process or a resource?",
        "Both",
        ['attention']
    )
    
    add_card(deck,
        "What process aspects does attention have?",
        "Orienting, selecting, gating",
        ['attention']
    )
    
    add_card(deck,
        "What resource aspect does attention have?",
        "Limited capacity",
        ['attention']
    )
    
    add_bidirectional(deck,
        "Arousal",
        "Generalized sense of alertness",
        ['attention', 'arousal']
    )
    
    add_bidirectional(deck,
        "Sustained attention",
        "Duration of focus; vigilance",
        ['attention', 'sustained']
    )
    
    add_bidirectional(deck,
        "Selective attention",
        "Prioritization of information among competing representations",
        ['attention', 'selective']
    )
    
    add_bidirectional(deck,
        "Divided attention",
        "Allocation of resources between different tasks",
        ['attention', 'divided']
    )
    
    add_card(deck,
        "Name the three types of selective attention",
        "Spatial, feature-based, object-based",
        ['attention', 'selective']
    )
    
    add_card(deck,
        "How quickly does endogenous attention deploy?",
        "At least 300 ms (slow)",
        ['attention', 'endogenous']
    )
    
    add_card(deck,
        "How long does endogenous attention last?",
        "Sustained",
        ['attention', 'endogenous']
    )
    
    add_card(deck,
        "How quickly does exogenous attention deploy?",
        "50-150 ms (quick)",
        ['attention', 'exogenous']
    )
    
    add_card(deck,
        "How long does exogenous attention last?",
        "Short-lived",
        ['attention', 'exogenous']
    )
    
    add_card(deck,
        "Does overt attention involve eye movements?",
        "Yes",
        ['attention', 'overt']
    )
    
    add_card(deck,
        "Does covert attention involve eye movements?",
        "No",
        ['attention', 'covert']
    )
    
    add_card(deck,
        "Name the three components of the attention working model",
        "Alertness, (Re)Orienting, Executive",
        ['attention', 'model']
    )
    
    # ===== ATTENTION BRAIN AREAS =====
    
    add_card(deck,
        "What does the RAS provide for attention?",
        "General state of alertness; phasic alertness",
        ['attention', 'RAS']
    )
    
    add_card(deck,
        "What happens with RAS lesion?",
        "Coma (zero arousal)",
        ['attention', 'RAS']
    )
    
    add_card(deck,
        "Can you have attention deficits while awake?",
        "Yes",
        ['attention']
    )
    
    add_card(deck,
        "Can extreme arousal impair attention?",
        "Yes (impairs flexibility)",
        ['attention', 'arousal']
    )
    
    add_card(deck,
        "What does the Superior Colliculus control?",
        "Visual fixation/foveation; saccadic eye movements",
        ['attention', 'SC']
    )
    
    add_card(deck,
        "What thalamic nuclei are involved in arousal and vigilance?",
        "Medial dorsal, reticular, and intralaminar nuclei",
        ['attention', 'thalamus']
    )
    
    add_card(deck,
        "What thalamic nucleus is involved in sensory gating?",
        "Pulvinar nucleus",
        ['attention', 'thalamus']
    )
    
    add_card(deck,
        "What happens with thalamus damage?",
        "Poor sensory gating (cannot selectively attend)",
        ['attention', 'thalamus']
    )
    
    add_card(deck,
        "What does the parietal lobe do for attention?",
        "Binds stimulus attributes (what + where); visuospatial aspects; attentional allocation",
        ['attention', 'parietal']
    )
    
    add_card(deck,
        "What does SPL damage affect?",
        "Shifts of spatial attention",
        ['attention', 'parietal']
    )
    
    add_card(deck,
        "What does IPL/TPJ damage cause?",
        "Spatial neglect",
        ['attention', 'parietal']
    )
    
    add_card(deck,
        "What is the frontal lobe's role in attention?",
        "High-level executive control; dividing attention between tasks",
        ['attention', 'frontal']
    )
    
    # ===== ATTENTION EFFECTS =====
    
    add_card(deck,
        "How does attention affect neural activity in relevant neurons?",
        "Enhances activity for attended vs unattended locations/features/objects",
        ['attention', 'effects']
    )
    
    add_card(deck,
        "What happens to synchronization between pulvinar and cortex with attention?",
        "Increases",
        ['attention', 'effects']
    )
    
    add_card(deck,
        "What happens to alpha band EEG power with increased spiking?",
        "Reduced oscillatory power (8-15 Hz)",
        ['attention', 'effects']
    )
    
    # ===== NEGLECT =====
    
    add_card(deck,
        "What side of space fails in neglect?",
        "Side opposite the lesion",
        ['neglect']
    )
    
    add_card(deck,
        "Can neglect be explained by visual, sensory, or motor deficits?",
        "No",
        ['neglect']
    )
    
    add_card(deck,
        "What hemisphere damage typically causes left neglect?",
        "Right hemisphere",
        ['neglect']
    )
    
    add_card(deck,
        "Where is damage in neglect?",
        "Inferior parietal or superior temporal lobe (TPJ) or ventral frontal cortex",
        ['neglect']
    )
    
    add_card(deck,
        "Can hemianopia patients compensate by turning their head?",
        "Yes",
        ['neglect', 'hemianopia']
    )
    
    add_card(deck,
        "Can neglect patients compensate by turning their head?",
        "No (unawareness of left side of space)",
        ['neglect']
    )
    
    add_card(deck,
        "Can neglected stimuli influence behavior unconsciously?",
        "Yes (burning house experiment; priming)",
        ['neglect']
    )
    
    add_card(deck,
        "Name one attentional hypothesis of neglect",
        "Inattention/unawareness, ipsilesional bias, or inability to disengage",
        ['neglect', 'theories']
    )
    
    add_card(deck,
        "What is the representational theory of neglect?",
        "Failure to construct complete mental representation of contralesional space",
        ['neglect', 'theories']
    )
    
    add_card(deck,
        "According to Heilman & Mesulam, which hemisphere is dominant for arousal?",
        "Right hemisphere",
        ['neglect', 'theories']
    )
    
    add_card(deck,
        "Can the right hemisphere direct attention to both hemispaces?",
        "Yes",
        ['neglect', 'theories']
    )
    
    add_card(deck,
        "Can the left hemisphere direct attention to both hemispaces?",
        "No, only to contralateral space",
        ['neglect', 'theories']
    )
    
    add_card(deck,
        "According to Posner, what is neglect a disorder of?",
        "Orienting (failure to disengage from right-sided stimuli)",
        ['neglect', 'theories']
    )
    
    add_bidirectional(deck,
        "Extinction (in neglect)",
        "Aware of left stimuli alone, but extinguish when right stimuli presented simultaneously",
        ['neglect', 'extinction']
    )
    
    add_card(deck,
        "What supports the representational deficit theory of neglect?",
        "Hallucinations show same bias; Bisiach & Luzzati patients described scenes with left omissions in both viewing directions",
        ['neglect', 'theories']
    )
    
    add_card(deck,
        "What often remains after neglect recovery?",
        "Simultagnosia and/or extinction",
        ['neglect', 'recovery']
    )
    
    # ===== BALINT'S SYNDROME =====
    
    add_bidirectional(deck,
        "Simultagnosia",
        "Inability to perceive visual field as whole; can only perceive one object at a time",
        ['Balint', 'simultagnosia']
    )
    
    add_bidirectional(deck,
        "Ocular apraxia",
        "Inability to make voluntary eye movements",
        ['Balint', 'apraxia']
    )
    
    add_bidirectional(deck,
        "Optic ataxia",
        "Inability to make visually guided hand movements",
        ['Balint', 'ataxia']
    )
    
    add_card(deck,
        "Where is damage in Balint's syndrome?",
        "Bilateral posterior parietal and occipital cortex",
        ['Balint']
    )
    
    add_card(deck,
        "Is Balint's damage unilateral or bilateral?",
        "Bilateral cortical lesions",
        ['Balint']
    )
    
    add_card(deck,
        "Is neglect damage unilateral or bilateral?",
        "Unilateral cortical (or subcortical) lesions",
        ['neglect', 'Balint']
    )
    
    # Shuffle and save
    random.shuffle(deck.notes)
    
    output_path = OUTPUT_DIR / 'PSYC3250M_Midterm_Recall_Optimized.apkg'
    genanki.Package(deck).write_to_file(str(output_path))
    
    print(f"\n✓ Created recall-optimized Anki deck with {len(deck.notes)} cards")
    print(f"✓ Cards are shuffled and optimized for self-testing")
    print(f"✓ Atomic questions with clear, testable prompts")
    print(f"✓ Saved to: {output_path}")
    print(f"\nKey improvements:")
    print(f"  - Questions test specific knowledge, not just lists")
    print(f"  - Active recall format (not passive recognition)")
    print(f"  - Bidirectional only when it aids learning")
    print(f"  - Clear, unambiguous wording")
    print(f"\nGood luck on your midterm!")

if __name__ == '__main__':
    main()
