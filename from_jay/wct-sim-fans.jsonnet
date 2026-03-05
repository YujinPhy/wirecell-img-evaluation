local g = import "pgraph.jsonnet";
local f = import "pgrapher/common/funcs.jsonnet";
local wc = import "wirecell.jsonnet";

local io = import 'pgrapher/common/fileio.jsonnet';
local tools_maker = import 'pgrapher/common/tools.jsonnet';
local params = import 'pgrapher/experiment/protodunevd/simparams.jsonnet';
local fcl_params = {
    use_dnnroi: false,
};

local tools = tools_maker(params);
local tools_all = tools_maker(params);
local tools = tools_all {anodes: [tools_all.anodes[n] for n in [6]]};

local sim_maker = import 'pgrapher/experiment/protodunevd/sim.jsonnet';
local sim = sim_maker(params, tools);

// Deposit and drifter ///////////////////////////////////////////////////////////////////////////////

local thetaXZ = 20*wc.deg;
local thetaXZ2 = 45*wc.deg;
local thetaXZ3 = 60*wc.deg;

local stubby_bottom = {
  head: wc.point(-50, 50, 50, wc.cm),
//  tail: wc.point(100*(1 + std.tan(thetaXZ)), 100, 100*(1+1), wc.cm),
  tail: wc.point(50*(1 + std.tan(thetaXZ)), 50, 50*(1+1), wc.cm),
};

local stubby_top = {
  head: wc.point(50, 50, 50, wc.cm),
//  tail: wc.point(100*(1 + std.tan(thetaXZ)), 100, 100*(1+1), wc.cm),
  tail: wc.point(50*(1 + std.tan(thetaXZ)), 50, 50*(1+1), wc.cm),
};

local stubby_top2 = {
  head: wc.point(105, 105, 105, wc.cm),
  tail: wc.point(105*(1 + std.tan(thetaXZ2)), 105, 105*(1+1), wc.cm),
};

local stubby_top3 = {
  head: wc.point(110, 110, 110, wc.cm),
  tail: wc.point(110*(1 + std.tan(thetaXZ3)), 110, 110*(1+1), wc.cm),
};

local isochronous = {
    head: wc.point(50, 50, 50, wc.cm),
    tail: wc.point(50, 50, 100, wc.cm),
};

local tracklist = [

  {
    time: 0 * wc.us,
    charge: -500, // 5000 e/mm
    ray: isochronous, // params.det.bounds,
  },

//  {
//    time: 0 * wc.us,
//    charge: -500, // 5000 e/mm
//    ray: stubby_top2, // params.det.bounds,
//  },

//  {
//    time: 0 * wc.us,
//    charge: -500, // 5000 e/mm
//    ray: stubby_top3, // params.det.bounds,
//  },

//  {
//    time: 0 * wc.us,
//    charge: -500,
//    ray: stubby_bottom,
//  },

];

// local depos = sim.tracks(tracklist, step=1.0 * wc.mm);
local depos = sim.tracks(tracklist, step=0.1 * wc.mm);


local drifter = sim.drifter;
local bagger = sim.make_bagger();

// Parallel part //////////////////////////////////////////////////////////////////////////////


// local sn_pipes = sim.signal_pipelines;
local sn_pipes = sim.splusn_pipelines;

local sp_maker = import 'pgrapher/experiment/protodunevd/sp.jsonnet';
local sp_override = {
    sparse: false,
    use_roi_debug_mode: false,
    use_multi_plane_protection: false,
    mp_tick_resolution: 4,
};
local sp = sp_maker(params, tools, sp_override);
local sp_pipes = [sp.make_sigproc(a) for a in tools.anodes];

local img = import 'img.jsonnet';
local img_maker = img();
local img_pipes = [img_maker.per_anode(a) for a in tools.anodes];

local magoutput = 'mag-sim-sp.root';
local magnify = import 'pgrapher/experiment/protodunevd/magnify-sinks.jsonnet';
local sinks = magnify(tools, magoutput);
local frame_tap = function(name, outname, tags, digitize) {
    ret: g.fan.tap('FrameFanout',  g.pnode({
        type: "FrameFileSink",
        name: name,
        data: {
            outname: outname,
            tags: tags,
            digitize: digitize,
        },  
    }, nin=1, nout=0), name),
}.ret;
local frame_sink = function(name, outname, tags, digitize) {
    ret: g.pnode({
        type: "FrameFileSink",
        name: name,
        data: {
            outname: outname,
            tags: tags,
            digitize: digitize,
        },
    }, nin=1, nout=0),
}.ret;

// local dnnroi = import 'pgrapher/experiment/protodunevd/dnnroi.jsonnet';
// local ts = {
//     type: "TorchService",
//     name: "dnnroi",
//     data: {
//         model: "ts-model/unet-l23-cosmic500-e50.ts",
//         device: "gpucpu",
//         concurrency: 1,
//     },
// };

local parallel_pipes = [
  g.pipeline([ 
                sn_pipes[n],
                // frame_tap(
                //     name="orig%d"%tools.anodes[n].data.ident,
                //     outname="frame-orig%d.tar.bz2"%tools.anodes[n].data.ident,
                //     tags=["orig%d"%tools.anodes[n].data.ident],
                //     digitize=true
                // ),
                // sinks.orig_pipe[n],
                sp_pipes[n],
                // frame_tap(
                //     name="gauss%d"%tools.anodes[n].data.ident,
                //     outname="frame-gauss%d.tar.bz2"%tools.anodes[n].data.ident,
                //     tags=["gauss%d"%tools.anodes[n].data.ident],
                //     digitize=false
                // ),
                sinks.decon_pipe[n],
                // sinks.debug_pipe[n], // use_roi_debug_mode=true in sp.jsonnet
                // dnnroi(tools.anodes[n], ts, output_scale=1.2),
                // sinks.dnnroi_pipe[n],
                // g.pnode({type: "DumpFrames", name: "dumpframes-%d"%tools.anodes[n].data.ident}, nin = 1, nout=0),
                img_pipes[n],
                // img_maker.sink(tools.anodes[n], "reco-%d"%tools.anodes[n].data.ident),
          ], 
          'parallel_pipe_%d' % n) 
  for n in std.range(0, std.length(tools.anodes) - 1)];

// local outtags = [];
local tag_rules = {
    frame: {
        '.*': 'framefanin',
    },
    trace: {['gauss%d' % anode.data.ident]: ['gauss%d' % anode.data.ident] for anode in tools.anodes}
        + {['wiener%d' % anode.data.ident]: ['wiener%d' % anode.data.ident] for anode in tools.anodes}
        + {['threshold%d' % anode.data.ident]: ['threshold%d' % anode.data.ident] for anode in tools.anodes}
        + {['dnnsp%d' % anode.data.ident]: ['dnnsp%d' % anode.data.ident] for anode in tools.anodes},
};

// // local parallel_graph = f.multifanout('DepoSetFanout', parallel_pipes, [1,4], [4,1], 'sn_mag', tag_rules);

// local nanodes = std.length(tools.anodes);
// local parallel_graph = f.multifanout('DepoSetFanout', parallel_pipes, [1,nanodes], [nanodes,1], 'sn_mag', tag_rules);

local dsout(name, multiplicity) = g.pnode({
    type: "DepoSetFanout",
    name: "dsout-%s" % name,
    data: {
        multiplicity: multiplicity,
    },
}, nin=1, nout=multiplicity);

local per_apa = [
    local dsf = dsout("bdf-%d" %n, 2);
    local reco = parallel_pipes[n];
    local cf = img_maker.cluster_fanout("bdf-%d"%tools.anodes[n].data.ident, 2);
    local bdf = img_maker.blob_depo_fill(tools.anodes[n], "bdf-%d"%tools.anodes[n].data.ident);
    local recs = img_maker.sink(tools.anodes[n], "reco-%d"%tools.anodes[n].data.ident);
    local bdfs = img_maker.sink(tools.anodes[n], "bdf-%d"%tools.anodes[n].data.ident);
    g.intern(
        [dsf],[],[reco,cf,bdf,recs,bdfs,],
        edges = [
            g.edge(dsf, reco, 0, 0),
            g.edge(dsf, bdf, 1, 1),
            g.edge(reco, cf, 0, 0),
            g.edge(cf, recs, 0, 0),
            g.edge(cf, bdf, 1, 0),
            g.edge(bdf, bdfs, 0, 0),
        ],
        iports = [dsf.iports[0]],
        oports = [],
    ), for n in std.range(0, std.length(tools.anodes) - 1)];

local parallel_graph = g.fan.fanout('DepoSetFanout', per_apa, "reco-bdf", tag_rules);

// Only one sink ////////////////////////////////////////////////////////////////////////////


local sink = sim.frame_sink;


// Final pipeline //////////////////////////////////////////////////////////////////////////////

// local graph = g.pipeline([depos, drifter, bagger, parallel_graph, sink], "main");
local graph = g.pipeline([depos, drifter, bagger, parallel_graph], "main");
// local graph = g.pipeline([depos, drifter, bagger, parallel_pipes[0]], "main");

local app = {
  type: 'Pgrapher', //Pgrapher, TbbFlow
  data: {
    edges: g.edges(graph),
  },
};

local cmdline = {
    type: "wire-cell",
    data: {
        // plugins: ["WireCellGen", "WireCellPgraph", "WireCellSio", "WireCellSigProc", "WireCellRoot", "WireCellTbb", "WireCellImg", "WireCellPytorch"],
        plugins: ["WireCellGen", "WireCellPgraph", "WireCellSio", "WireCellSigProc", "WireCellRoot", "WireCellTbb", "WireCellImg"],
        apps: ["Pgrapher"]
    }
};

[cmdline] + g.uses(graph) + [app]
