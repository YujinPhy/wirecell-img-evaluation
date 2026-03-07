local g = import 'pgraph.jsonnet';
local f = import 'pgrapher/common/funcs.jsonnet';
local wc = import 'wirecell.jsonnet';
local io = import 'pgrapher/common/fileio.jsonnet';
local tools_maker = import 'pgrapher/common/tools.jsonnet';

local util = import 'pgrapher/experiment/pdhd/funcs.jsonnet';
local params = import 'pgrapher/experiment/pdhd/simparams.jsonnet';


// local tools = tools_maker(params);
local btools = tools_maker(params);
local tools = btools {
    // anodes : [btools.anodes[0],],
    anodes : [btools.anodes[0], btools.anodes[1],],
    // anodes : [btools.anodes[0], btools.anodes[1], btools.anodes[2], btools.anodes[3],],
};

local sim_maker = import 'pgrapher/experiment/pdhd/sim.jsonnet';
local sim = sim_maker(params, tools);

local nanodes = std.length(tools.anodes);
local anode_iota = std.range(0, nanodes-1);

// ==== Track Definition ====
local thetaXZ = 45*wc.deg;
local singletrk_apa1 = {
tail: wc.point(-100, 100, 100, wc.cm),
head: wc.point(-100*(1 + std.tan(thetaXZ)), 100, 100*(1+1), wc.cm),
};

local singletrk_apa2 = {
tail: wc.point(100, 100, 100, wc.cm),
head: wc.point(100*(1 + std.tan(thetaXZ)), 100, 100*(1+1), wc.cm),
};

local tracklist = [

{
    time: 0 * wc.us,
    charge: -500, // negative means # electrons per step (see below configuration) 
    // ray: singletrk_apa1, // params.det.bounds,
    ray: singletrk_apa2, // params.det.bounds,
},

];

local track_depos = sim.tracks(tracklist, step=0.1 * wc.mm);


// ==== Bagger & Drifter ====
local drifter = sim.drifter;
local bagger = sim.make_bagger("bagger");


// ==== NF + Trad SP + Img ====
// signal plus noise pipelines
//local sn_pipes = sim.signal_pipelines;
local sn_pipes = sim.splusn_pipelines;

// local perfect = import 'pgrapher/experiment/pdhd/chndb-perfect.jsonnet';
local base = import 'pgrapher/experiment/pdhd/chndb-base.jsonnet';
local chndb = [{
type: 'OmniChannelNoiseDB',
name: 'ocndbperfect%d' % n,
// data: perfect(params, tools.anodes[n], tools.field, n),
data: base(params, tools.anodes[n], tools.field, n),
uses: [tools.anodes[n], tools.field],  // pnode extension
} for n in anode_iota];

//local chndb_maker = import 'pgrapher/experiment/pdhd/chndb.jsonnet';
//local noise_epoch = "perfect";
//local noise_epoch = "after";
//local chndb_pipes = [chndb_maker(params, tools.anodes[n], tools.fields[n]).wct(noise_epoch)
//                for n in std.range(0, std.length(tools.anodes)-1)];
local nf_maker = import 'pgrapher/experiment/pdhd/nf.jsonnet';
// local nf_pipes = [nf_maker(params, tools.anodes[n], chndb_pipes[n]) for n in std.range(0, std.length(tools.anodes)-1)];
local nf_pipes = [nf_maker(params, tools.anodes[n], chndb[n], n, name='nf%d' % n) for n in anode_iota];

local sp_maker = import 'pgrapher/experiment/pdhd/sp.jsonnet';
local sp_override = { // assume all tages sets in base sp.jsonnet
    sparse: false, // sigoutform == 'sparse',
    // sparse: true, // sigoutform == 'sparse',
    // wiener_tag: "",
    // gauss_tag: "",
    use_roi_refinement: true,
    use_roi_debug_mode: true,
    save_negtive_charge: false, // no negative charge in gauss
    tight_lf_tag: "",
    loose_lf_tag: "",
    // cleanup_roi_tag: "",
    break_roi_loop1_tag: "",
    break_roi_loop2_tag: "",
    shrink_roi_tag: "",
    // extend_roi_tag: "",
    // decon_charge_tag: "",
    use_multi_plane_protection: true,
    do_not_mp_protect_traditional: true, // do_not_mp_protect_traditional to
                                        // make a clear ref, defualt is false
    mp_tick_resolution: 10,
    MP_feature_val_method: 1,
};

// local sp = sp_maker(params, tools, { sparse: true, });
// local sp = sp_maker(params, tools, { sparse: true, use_roi_debug_mode: true, use_multi_plane_protection: true, mp_tick_resolution: 4, });
local sp = sp_maker(params, tools, sp_override);
local sp_pipes = [sp.make_sigproc(a) for a in tools.anodes];

local img = import '/nfs/data/1/yujin/img_BlobDepoFill/wct-sim/img.jsonnet';
local img_maker = img();
local img_pipes = [img_maker.per_anode(a) for a in tools.anodes];

local rng = tools.random;
local magoutput = 'pdhd-sim-check-deposplat.root';
local magnify = import 'pgrapher/experiment/pdhd/magnify-sinks.jsonnet';
local magnifyio = magnify(tools, magoutput);

local hio_truth = [g.pnode({
        type: 'HDF5FrameTap',
        name: 'hio_truth%d' % n,
        data: {
            anode: wc.tn(tools.anodes[n]),
            trace_tags: ['deposplat%d'%n],
            filename: "g4-tru-%d.h5" % n,
            chunk: [0, 0], // ncol, nrow
            gzip: 2,
            high_throughput: true,
        },  
    }, nin=1, nout=1),
    for n in std.range(0, std.length(tools.anodes) - 1)
];

local hio_orig = [g.pnode({
        type: 'HDF5FrameTap',
        name: 'hio_orig%d' % n,
        data: {
            anode: wc.tn(tools.anodes[n]),
            trace_tags: ['orig%d'%n],
            filename: "g4-rec-%d.h5" % n,
            chunk: [0, 0], // ncol, nrow
            gzip: 2,
            high_throughput: true,
        },  
    }, nin=1, nout=1),
    for n in std.range(0, std.length(tools.anodes) - 1)
];

local hio_sp = [g.pnode({
        type: 'HDF5FrameTap',
        name: 'hio_sp%d' % n,
        data: {
            anode: wc.tn(tools.anodes[n]),
            trace_tags: ['loose_lf%d' % n
            , 'tight_lf%d' % n
            , 'cleanup_roi%d' % n
            , 'break_roi_1st%d' % n
            , 'break_roi_2nd%d' % n
            , 'shrink_roi%d' % n
            , 'extend_roi%d' % n
            , 'mp3_roi%d' % n
            , 'mp2_roi%d' % n
            , 'decon_charge%d' % n
            , 'gauss%d' % n],
            filename: "g4-rec-%d.h5" % n,
            chunk: [0, 0], // ncol, nrow
            gzip: 2,
            high_throughput: true,
        },  
    }, nin=1, nout=1),
    for n in std.range(0, std.length(tools.anodes) - 1)
];

local hio_dnn = [g.pnode({
        type: 'HDF5FrameTap',
        name: 'hio_dnn%d' % n,
        data: {
            anode: wc.tn(tools.anodes[n]),
            // trace_tags: ['dnn_sp%d' % n],
            trace_tags: ['dnnsp%d' % n],
            filename: "g4-rec-%d.h5" % n,
            chunk: [0, 0], // ncol, nrow
            gzip: 2,
            high_throughput: true,
        },  
    }, nin=1, nout=1),
    for n in std.range(0, std.length(tools.anodes) - 1)
];

local rio_orig = [g.pnode({
        type: 'ExampleROOTAna',
        name: 'rio_orig_apa%d' % n,
        data: {
            output_filename: "g4-rec-%d.root" % n,
            anode: wc.tn(tools.anodes[n]),
        },  
    }, nin=1, nout=1),
    for n in std.range(0, std.length(tools.anodes) - 1)
];

local rio_nf = [g.pnode({
        type: 'ExampleROOTAna',
        name: 'rio_nf_apa%d' % n,
        data: {
            output_filename: "g4-rec-%d.root" % n,
            anode: wc.tn(tools.anodes[n]),
        },  
    }, nin=1, nout=1),
    for n in std.range(0, std.length(tools.anodes) - 1)
];

local rio_sp = [g.pnode({
        type: 'ExampleROOTAna',
        name: 'rio_sp_apa%d' % n,
        data: {
            output_filename: "g4-rec-%d.root" % n,
            anode: wc.tn(tools.anodes[n]),
        },  
    }, nin=1, nout=1),
    for n in std.range(0, std.length(tools.anodes) - 1)
];

local reco_fork = [
    g.pipeline([
                sn_pipes[n],
                magnifyio.orig_pipe[n],
                // hio_orig[n],
                nf_pipes[n],
                // rio_nf[n],
                sp_pipes[n],
                // hio_sp[n],
                // rio_sp[n],
                magnifyio.debug_pipe[n],
                magnifyio.decon_pipe[n],

                img_pipes[n],
                ],
                'reco_fork%d' % n)
    for n in anode_iota
];


// ==== Connecting pipes ====
local tag_rules = {
    frame: {
        '.*': 'framefanin',
    },
    trace: {['gauss%d' % anode.data.ident]: ['gauss%d' % anode.data.ident] for anode in tools.anodes}
        + {['wiener%d' % anode.data.ident]: ['wiener%d' % anode.data.ident] for anode in tools.anodes}
        + {['threshold%d' % anode.data.ident]: ['threshold%d' % anode.data.ident] for anode in tools.anodes}
        + {['dnnsp%d' % anode.data.ident]: ['dnnsp%d' % anode.data.ident] for anode in tools.anodes},
};

local pre_pipe = g.pipeline([track_depos, drifter, bagger]);


local dsout(name, multiplicity) = g.pnode({
    type: "DepoSetFanout",
    name: "dsout-%s" % name,
    data: {
        multiplicity: multiplicity,
    },
}, nin=1, nout=multiplicity
);

local drifted_depo_sink(name, n) = g.pnode({
    type: "DepoFileSink",
    name: "drifted_depo_sink-%s" % name,
    data: { 
        outname: "depos-drifted-%d.zip" % n 
    }
}, nin=1, nout=0);

local per_apa = [
    local dsf = dsout("bdf-%d" %n, 3);
    local drifted_depos = drifted_depo_sink("drfited-%d" %n, n);
    local reco = reco_fork[n];
    local cf = img_maker.cluster_fanout("bdf-%d"%tools.anodes[n].data.ident, 2);
    local bdf = img_maker.blob_depo_fill(tools.anodes[n], "bdf-%d"%tools.anodes[n].data.ident);
    local recs = img_maker.sink(tools.anodes[n], "%d"%tools.anodes[n].data.ident);
    local bdfs = img_maker.sink(tools.anodes[n], "bdf-%d"%tools.anodes[n].data.ident);
    g.intern(
        innodes=[dsf],
        outnodes=[],
        centernodes=[drifted_depos, reco,cf,bdf,recs,bdfs,],
        edges = [
            g.edge(dsf, reco, 0, 0),
            g.edge(dsf, bdf, 1, 1),
            g.edge(dsf, drifted_depos, 2, 0),
            g.edge(reco, cf, 0, 0),
            g.edge(cf, recs, 0, 0),
            g.edge(cf, bdf, 1, 0),
            g.edge(bdf, bdfs, 0, 0),
        ],
        iports = [dsf.iports[0]],
        oports = [],
    ), for n in std.range(0, std.length(tools.anodes) - 1)];

local parallel_graph = g.fan.fanout('DepoSetFanout', per_apa, "reco-bdf", tag_rules);
local graph = g.pipeline([pre_pipe, parallel_graph], "main");

local app = {
type: 'Pgrapher',
data: {
    edges: g.edges(graph),
},
};

local cmdline = { 
    type: "wire-cell",
    data: {
        plugins: ["WireCellPgraph", "WireCellGen","WireCellSio","WireCellSigProc","WireCellRoot","WireCellLarsoft","WireCellHio","WireCellTbb",'WireCellImg',"WireCellPytorch"],
        // plugins: ["WireCellGen", "WireCellPgraph", "WireCellSio", "WireCellSigProc", "WireCellRoot", "WireCellPytorch"],
        apps: ["Pgrapher"]
    }   
};
[cmdline] + g.uses(graph) + [app]

