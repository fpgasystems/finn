import os
import shutil
import numpy as np

import finn.builder.build_dataflow as build
import finn.builder.build_dataflow_config as build_cfg

unsw_nb15_data = np.load("./unsw_nb15_binarized.npz")

inp = unsw_nb15_data["train"][:, :-1]
inp = np.concatenate([inp, np.zeros((inp.shape[0], 7))], -1).astype(np.float32)
out = unsw_nb15_data["train"][:, -1].astype(np.float32)

indices = np.where(out == 0)[0][:1]

inp = 2 * inp[indices] - 1
out = 2 * out[indices] - 1

np.save(open("input.npy", "wb"), inp)
np.save(open("expected_output.npy", "wb"), out)

model_dir = os.environ['FINN_ROOT'] + "/notebooks/end2end_example/cybersecurity"
model_file = model_dir + "/cybsec-mlp-ready.onnx"

estimates_output_dir = "three_boards"

os.environ["RTLSIM_TRACE_DEPTH"] = "3"

steps = [
    "step_qonnx_to_finn",
    "step_tidy_up",
    "step_streamline",
    "step_convert_to_hls",
    "step_create_dataflow_partition",
    "step_target_fps_parallelization",
    "step_apply_folding_config",
    "step_minimize_bit_width",
    "step_assign_partition_ids",
    "step_insert_accl",
    "step_split_dataflow",
    "step_generate_estimate_reports",
    "step_hls_codegen",
    "step_hls_ipgen",
    # "step_set_fifo_depths",
    "step_create_stitched_ip",
]

cfg_splits = build.DataflowBuildConfig(
    verbose             = True,
    output_dir          = estimates_output_dir,
    steps               = steps,
    mvau_wwidth_max     = 80,
    target_fps          = 1000000,
    synth_clk_period_ns = 10.0,
    generate_outputs    = [
        build_cfg.DataflowOutputType.ESTIMATE_REPORTS,
        build_cfg.DataflowOutputType.STITCHED_IP,
    ],
    stitched_ip_gen_dcp = True,
    verify_steps        = [build_cfg.VerificationStepType.FOLDED_HLS_CPPSIM],
    shell_flow_type     = build_cfg.ShellFlowType.VITIS_ALVEO,
    board               = "U55C",
    num_boards          = 3,
    # start_step="step_create_stitched_ip",
    save_intermediate_models = True,
)

build.build_distributed_dataflow_cfg(model_file, cfg_splits)

