#include "ctxfuzz.h"
#include "scen_matrix.h"
#include "scen_gain.h"
#include "scen_haas.h"
#include "scen_clipper.h"
#include "scen_gate.h"
#include "scen_quickeq.h"
#include "scen_qemath.h"
#include "scen_resonator.h"
#include "scen_stereo.h"
#include "scen_disperser.h"
#include "scen_formant.h"
#include "scen_khmath.h"
#include "scen_phaser.h"
#include "scen_delay.h"
#include "scen_limiter.h"
#include "scen_ladder.h"
Scenario SCEN_LIST[] = {
    {"matrix", trial_matrix, 6},
    {"gain", trial_gain, 6},
    {"haas", trial_haas, 6},
    {"clipper", trial_clipper, 6},
    {"gate", trial_gate, 6},
    {"quickeq", trial_quickeq, 6},
    {"qemath", trial_qemath, 96},
    {"qebig", trial_qebig, 96},
    {"qeclass", trial_qeclass, 20},
    {"qeclass2", trial_qeclass2, 12},
    {"resonator", trial_resonator, 6},
    {"stereo", trial_stereo, 6},
    {"disperser", trial_disperser, 6},
    {"formant", trial_formant, 6},
    {"khmath", trial_khmath, 60},
    {"khalloc", trial_khalloc, 24},
    {"khvec", trial_khvec, 16},
    {"khicall", trial_khicall, 16},
    {"khprobe", trial_khprobe, 12},
    {"phaser", trial_phaser, 6},
    {"delay", trial_delay, 6},
    {"limiter", trial_limiter, 6},
    {"ladder", trial_ladder, 6},
    {0, 0, 0},
};
