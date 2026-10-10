#include "ctxfuzz.h"
#include "scen_matrix.h"
#include "scen_gain.h"
#include "scen_haas.h"
#include "scen_clipper.h"
#include "scen_gate.h"
#include "scen_quickeq.h"
#include "scen_qemath.h"
#include "scen_em.h"
Scenario SCEN_LIST[] = {
    {"matrix", trial_matrix, 6},
    {"gain", trial_gain, 6},
    {"haas", trial_haas, 6},
    {"clipper", trial_clipper, 6},
    {"gate", trial_gate, 6},
    {"quickeq", trial_quickeq, 6},
    {"qemath", trial_qemath, 96},
    {"qeclass", trial_qeclass, 20},
    {"qeclass2", trial_qeclass2, 12},
    {"em", trial_em, 6},
    {"empoll", trial_empoll, 20},
    {0, 0, 0},
};
