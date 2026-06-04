"""HTML templates for the World Explorer web UI."""

UI_HTML = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BRING — World Engine</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Doto:wght@400;500;600;700&family=Space+Grotesk:wght@300;400;500;700&family=Space+Mono:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js"></script>
<style>
:root {
  --black: #000000;
  --surface: #080808;
  --surface-raised: #111111;
  --surface-hover: #161616;
  --border: #1A1A1A;
  --border-visible: #272727;
  --border-strong: #353535;
  --text-disabled: #444444;
  --text-tertiary: #5E5E5E;
  --text-secondary: #888888;
  --text-primary: #CCCCCC;
  --text-display: #FFFFFF;
  --accent: #D71921;
  --accent-subtle: rgba(215,25,33,0.10);
  --accent-glow: rgba(215,25,33,0.20);
  --success: #4A9E5C;
  --success-subtle: rgba(74,158,92,0.12);
  --warning: #D4A843;
  --warning-subtle: rgba(212,168,67,0.12);
  --interactive: #5B9BF6;
  --interactive-subtle: rgba(91,155,246,0.10);
  --font-display: 'Doto', 'Space Mono', monospace;
  --font-body: 'Space Grotesk', 'DM Sans', system-ui, sans-serif;
  --font-mono: 'Space Mono', monospace;
  --radius-xs: 2px;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 999px;
  --ease-out: cubic-bezier(0.22, 0.61, 0.36, 1);
  --ease-mech: cubic-bezier(0.0, 0.0, 0.2, 1);
  --dur-instant: 60ms;
  --dur-fast: 120ms;
  --dur-normal: 200ms;
  --dur-slow: 340ms;
  --sidebar-w: 380px;
  --topbar-h: 40px;
  --input-h: 48px;
  --tab-h: 36px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{height:100%;background:var(--black);overflow:hidden}
body{height:100%;background:var(--black);font-family:var(--font-mono);font-size:12px;color:var(--text-primary);display:flex;flex-direction:column;overflow:hidden;user-select:none;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}

/* ═══════════ APP SHELL ═══════════ */
.app{position:relative;z-index:1;display:flex;height:100%;overflow:hidden}
.main-area{flex:1;display:flex;flex-direction:column;min-width:0;transition:padding-right var(--dur-slow) var(--ease-out);padding-right:0}
.app--sidebar-open .main-area{padding-right:var(--sidebar-w)}

/* ═══════════ TOPBAR ═══════════ */
.topbar{display:flex;align-items:center;gap:6px;padding:0 16px;height:var(--topbar-h);flex-shrink:0;border-bottom:1px solid var(--border);background:var(--black);z-index:10}
.topbar__brand{font-family:var(--font-mono);font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:var(--text-disabled);white-space:nowrap}
.topbar__brand span{color:var(--text-display);font-weight:700}
.topbar__sep{width:1px;height:14px;background:var(--border);flex-shrink:0}
.topbar__mem{display:flex;align-items:center;gap:5px;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-tertiary);white-space:nowrap;cursor:default}
.topbar__mem-dot{width:5px;height:5px;border-radius:50%;background:var(--success);flex-shrink:0;transition:background var(--dur-fast)}
.topbar__mem-dot--warn{background:var(--warning)}
.topbar__mem-dot--crit{background:var(--accent);animation:dotBlink 1s step-end infinite}
@keyframes dotBlink{0%,100%{opacity:1}50%{opacity:.2}}
.topbar__spacer{flex:1}
.topbar__st{display:flex;align-items:center;gap:3px;font-size:8px;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-disabled)}
.topbar__st::before{content:'';width:4px;height:4px;border-radius:50%;flex-shrink:0;background:var(--text-disabled);transition:background var(--dur-fast)}
.topbar__st--on{color:var(--text-secondary)}.topbar__st--on::before{background:var(--success)}
.topbar__st--warn{color:var(--warning)}.topbar__st--warn::before{background:var(--warning)}
.topbar__st--off{color:var(--text-disabled)}
.topbar__clock{font-size:10px;color:var(--text-disabled);letter-spacing:0.06em;white-space:nowrap;font-variant-numeric:tabular-nums}
.topbar__btn{background:transparent;border:1px solid var(--border-visible);color:var(--text-tertiary);font-family:var(--font-mono);font-size:8px;letter-spacing:0.12em;text-transform:uppercase;padding:4px 10px;cursor:pointer;border-radius:var(--radius-pill);transition:all var(--dur-fast);white-space:nowrap;display:flex;align-items:center;gap:4px;height:26px}
.topbar__btn:hover{border-color:var(--text-secondary);color:var(--text-primary)}
.topbar__btn--active{border-color:var(--text-display);color:var(--text-display);background:var(--surface-raised)}
.topbar__btn-dot{width:4px;height:4px;border-radius:50%;background:var(--accent);flex-shrink:0}

/* ═══════════ TERMINAL ═══════════ */
.terminal{flex:1;overflow-y:auto;overflow-x:hidden;padding:16px 24px 16px 24px;scroll-behavior:smooth;min-height:0;display:flex;flex-direction:column;gap:0}
.terminal::-webkit-scrollbar{width:2px}
.terminal::-webkit-scrollbar-track{background:transparent}
.terminal::-webkit-scrollbar-thumb{background:var(--border-visible);border-radius:2px}

/* Messages */
.msg{padding:3px 0;animation:msgIn 140ms var(--ease-out);line-height:1.6;word-break:break-word;white-space:pre-wrap}
.msg--dim{color:var(--text-secondary)}
.msg--accent{color:var(--accent)}
.msg--success{color:var(--success)}
.msg--warn{color:var(--warning)}
.msg--interactive{color:var(--interactive)}
.msg--hero{color:var(--text-display);font-family:var(--font-display);font-size:52px;font-variation-settings:"ROND" 22;font-weight:700;letter-spacing:-0.04em;line-height:1.0;padding:20px 0 8px}
.msg--heading{color:var(--text-display);font-weight:700;text-transform:uppercase;font-size:9px;letter-spacing:0.12em;padding-top:10px}
.msg--log{color:var(--text-disabled);font-size:11px;padding-left:16px;border-left:1px solid var(--border-visible);margin-left:4px}
.msg--narrative{color:var(--text-primary);font-family:var(--font-body);font-size:14px;line-height:1.7;padding:6px 0;letter-spacing:0.01em}
.msg--system{color:var(--text-secondary);font-size:11px;padding:2px 0}
.msg--system::before{content:'[SYS] ';color:var(--text-disabled);font-size:9px;letter-spacing:0.1em}
.msg--error{color:var(--accent)}
.msg--error::before{content:'[ERR] ';font-size:9px;letter-spacing:0.1em}

/* Timestamp on hover */
.msg__time{display:none;font-size:9px;color:var(--text-disabled);letter-spacing:0.06em;margin-left:8px;font-variant-numeric:tabular-nums}
.msg:hover .msg__time{display:inline}

@keyframes msgIn{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:translateY(0)}}

/* Inline blocks */
.iblock{border:1px solid var(--border);border-radius:var(--radius-md);padding:14px 16px;margin:6px 0;animation:msgIn 160ms var(--ease-out)}
.iblock__label{font-family:var(--font-mono);font-size:8px;text-transform:uppercase;letter-spacing:0.14em;color:var(--text-disabled);margin-bottom:10px;display:flex;align-items:center;gap:6px}
.iblock__label::after{content:'';flex:1;height:1px;background:var(--border)}
.iblock__grid{display:grid;gap:4px 20px}
.iblock__row{display:flex;justify-content:space-between;align-items:baseline;padding:2px 0;font-size:11px}
.iblock__row-label{font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-disabled)}
.iblock__row-value{color:var(--text-primary);font-family:var(--font-mono)}

/* Hero stat */
.hstat{display:flex;flex-direction:column;gap:2px}
.hstat__num{font-family:var(--font-display);font-size:36px;font-variation-settings:"ROND" 16;font-weight:600;color:var(--text-display);letter-spacing:-0.03em;line-height:1}
.hstat__unit{font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled)}
.hstat__pair{display:flex;gap:32px;flex-wrap:wrap}

/* Table */
.dtable{width:100%;border-collapse:collapse;font-size:11px}
.dtable th{font-family:var(--font-mono);font-size:8px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled);text-align:left;padding:6px 8px;border-bottom:1px solid var(--border-visible);font-weight:400}
.dtable td{padding:5px 8px;border-bottom:1px solid var(--border);color:var(--text-secondary)}
.dtable tr:hover td{color:var(--text-primary);background:var(--surface)}
.dtable__mono{font-family:var(--font-mono);font-variant-numeric:tabular-nums}
.dtable__link{color:var(--interactive);cursor:pointer;text-decoration:none;border-bottom:1px solid transparent;transition:border-color var(--dur-fast)}
.dtable__link:hover{border-bottom-color:var(--interactive)}

/* ═══════════ INPUT AREA ═══════════ */
.input-area{flex-shrink:0;border-top:1px solid var(--border);background:var(--black)}
.input-area__main{display:flex;align-items:center;gap:8px;padding:0 20px;height:var(--input-h)}
.input-area__caret{color:var(--accent);font-size:14px;flex-shrink:0;transition:opacity var(--dur-fast)}
.input-area__field{flex:1;background:transparent;border:none;outline:none;font-family:var(--font-mono);font-size:12px;color:var(--text-primary);caret-color:var(--text-display);letter-spacing:0.01em;padding:4px 0}
.input-area__field::placeholder{color:var(--text-disabled);font-style:italic}
.input-area__actions{display:flex;gap:4px;align-items:center}
.input-area__act{background:transparent;border:1px solid var(--border);color:var(--text-disabled);font-family:var(--font-mono);font-size:8px;letter-spacing:0.1em;text-transform:uppercase;padding:3px 8px;cursor:pointer;border-radius:var(--radius-pill);transition:all var(--dur-fast);white-space:nowrap}
.input-area__act:hover{border-color:var(--border-strong);color:var(--text-secondary)}

/* Quick commands */
.quick-cmds{display:flex;gap:4px;padding:0 20px 8px;overflow-x:auto;-ms-overflow-style:none;scrollbar-width:none}
.quick-cmds::-webkit-scrollbar{display:none}
.qcmd{background:transparent;border:1px solid var(--border);color:var(--text-disabled);font-family:var(--font-mono);font-size:8px;letter-spacing:0.08em;text-transform:uppercase;padding:3px 8px;cursor:pointer;border-radius:var(--radius-pill);transition:all var(--dur-fast);white-space:nowrap;flex-shrink:0}
.qcmd:hover{border-color:var(--border-strong);color:var(--text-secondary)}

/* ═══════════ SIDEBAR ═══════════ */
.sidebar{position:fixed;right:0;top:0;height:100%;width:var(--sidebar-w);background:var(--surface);border-left:1px solid var(--border-visible);z-index:50;transform:translateX(100%);transition:transform var(--dur-slow) var(--ease-out);display:flex;flex-direction:column;overflow:hidden}
.app--sidebar-open .sidebar{transform:translateX(0)}
.sidebar__tabs{display:flex;border-bottom:1px solid var(--border);flex-shrink:0;padding:0 8px;gap:0}
.sidebar__tab{font-family:var(--font-mono);font-size:8px;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-disabled);padding:0 10px;height:var(--tab-h);display:flex;align-items:center;cursor:pointer;border-bottom:2px solid transparent;transition:all var(--dur-fast);white-space:nowrap;background:transparent;border-top:none;border-left:none;border-right:none}
.sidebar__tab:hover{color:var(--text-secondary)}
.sidebar__tab--active{color:var(--text-display);border-bottom-color:var(--text-display)}
.sidebar__body{flex:1;overflow-y:auto;overflow-x:hidden;padding:12px;display:flex;flex-direction:column;gap:8px}
.sidebar__body::-webkit-scrollbar{width:2px}
.sidebar__body::-webkit-scrollbar-track{background:transparent}
.sidebar__body::-webkit-scrollbar-thumb{background:var(--border-visible);border-radius:2px}

/* Panel visibility */
.panel{display:none;flex-direction:column;gap:8px}
.panel--active{display:flex}

/* Widget stagger */
.sb-w{opacity:0;transform:translateY(6px);transition:opacity var(--dur-normal) var(--ease-out),transform var(--dur-normal) var(--ease-out)}
.sidebar--visible .sb-w{opacity:1;transform:translateY(0)}
.sidebar--visible .sb-w:nth-child(1){transition-delay:0ms}
.sidebar--visible .sb-w:nth-child(2){transition-delay:25ms}
.sidebar--visible .sb-w:nth-child(3){transition-delay:50ms}
.sidebar--visible .sb-w:nth-child(4){transition-delay:75ms}
.sidebar--visible .sb-w:nth-child(5){transition-delay:100ms}
.sidebar--visible .sb-w:nth-child(6){transition-delay:125ms}
.sidebar--visible .sb-w:nth-child(7){transition-delay:150ms}
.sidebar--visible .sb-w:nth-child(8){transition-delay:175ms}

/* ═══════════ WIDGET CARD ═══════════ */
.wcard{background:var(--surface-raised);border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px;transition:border-color var(--dur-fast)}
.wcard:hover{border-color:var(--border-visible)}
.wcard--expand{cursor:pointer}
.wcard__head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.wcard__title{font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-secondary)}
.wcard__chev{font-size:9px;color:var(--text-disabled);transition:transform var(--dur-fast);flex-shrink:0}
.wcard--expanded .wcard__chev{transform:rotate(90deg)}
.wcard__body{max-height:0;overflow:hidden;transition:max-height var(--dur-slow) var(--ease-out)}
.wcard--expanded .wcard__body{max-height:600px}
.wcard__body-inner{padding-top:10px;display:flex;flex-direction:column;gap:4px}

/* ═══════════ SEGMENTED PROGRESS ═══════════ */
.seg{width:100%}
.seg__track{display:flex;gap:2px;width:100%}
.seg__blk{flex:1;border-radius:var(--radius-xs);transition:background var(--dur-fast)}
.seg--hero .seg__blk{height:16px}
.seg--std .seg__blk{height:8px}
.seg--compact .seg__blk{height:4px}
.seg__blk--empty{background:var(--border)}
.seg__blk--fill{animation:segPop 100ms var(--ease-mech) backwards}
@keyframes segPop{from{transform:scaleY(0)}to{transform:scaleY(1)}}
.seg__readout{display:flex;align-items:baseline;justify-content:space-between;margin-top:4px}
.seg__val{font-family:var(--font-display);font-variation-settings:"ROND" 14;font-weight:600;color:var(--text-display);letter-spacing:-0.03em;line-height:1}
.seg--hero .seg__val{font-size:24px}
.seg--std .seg__val{font-size:16px}
.seg--compact .seg__val{font-family:var(--font-mono);font-size:10px;font-variation-settings:normal;font-weight:400;letter-spacing:0;color:var(--text-secondary)}
.seg__lbl{font-family:var(--font-mono);font-size:8px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled)}

/* ═══════════ SUBTASK ═══════════ */
.stask{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--text-secondary);padding:2px 0}
.stask__dot{width:4px;height:4px;border-radius:var(--radius-xs);flex-shrink:0;background:var(--border-visible)}
.stask__dot--done{background:var(--success)}
.stask__dot--active{background:var(--warning)}
.stask--done{opacity:.35;text-decoration:line-through}

/* ═══════════ STAT ROW ═══════════ */
.srow{display:flex;align-items:center;gap:8px;font-size:10px;padding:3px 0}
.srow__label{font-family:var(--font-mono);font-size:8px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled);width:52px;flex-shrink:0}
.srow__bar{flex:1}
.srow__val{font-family:var(--font-mono);font-size:10px;color:var(--text-secondary);width:32px;text-align:right;flex-shrink:0;font-variant-numeric:tabular-nums}

/* ═══════════ EVENT FEED ═══════════ */
.efeed{display:flex;flex-direction:column;gap:0}
.efeed__item{display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);font-size:10px;animation:msgIn 140ms var(--ease-out)}
.efeed__time{font-family:var(--font-mono);font-size:9px;color:var(--text-disabled);flex-shrink:0;font-variant-numeric:tabular-nums;letter-spacing:0.04em;min-width:36px}
.efeed__type{font-family:var(--font-mono);font-size:8px;text-transform:uppercase;letter-spacing:0.08em;flex-shrink:0;min-width:40px}
.efeed__type--memory{color:var(--interactive)}
.efeed__type--entity{color:var(--success)}
.efeed__type--edge{color:var(--warning)}
.efeed__type--system{color:var(--text-disabled)}
.efeed__text{color:var(--text-secondary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ═══════════ RELATIONSHIP CARD ═══════════ */
.rel-card{display:flex;flex-direction:column;gap:6px;padding:10px 0;border-bottom:1px solid var(--border)}
.rel-card:last-child{border-bottom:none}
.rel-card__names{font-family:var(--font-body);font-size:12px;color:var(--text-primary)}
.rel-card__status{font-family:var(--font-mono);font-size:9px;color:var(--text-disabled);text-transform:uppercase;letter-spacing:0.08em}

/* ═══════════ SPARKLINE ═══════════ */
.spark{display:flex;align-items:center;gap:12px}
.spark__label{font-family:var(--font-mono);font-size:8px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled);white-space:nowrap}
.spark__val{font-family:var(--font-display);font-size:20px;font-variation-settings:"ROND" 12;font-weight:600;color:var(--text-display);letter-spacing:-0.03em;line-height:1}

/* ═══════════ THINKING ═══════════ */
.thinking{font-family:var(--font-mono);font-size:10px;color:var(--text-disabled);display:flex;align-items:center;gap:5px;padding:3px 0;animation:msgIn 100ms var(--ease-out)}
.thinking__blks{display:inline-flex;gap:2px}
.thinking__b{width:3px;height:9px;background:var(--border-visible);border-radius:1px;transition:background 80ms}
.thinking__b--on{background:var(--text-display)}

/* ═══════════ COMMAND PALETTE ═══════════ */
.palette{position:fixed;inset:0;z-index:200;display:none;align-items:flex-start;justify-content:center;padding-top:15vh;background:rgba(0,0,0,0.85);animation:paletteIn 120ms var(--ease-out)}
.palette--open{display:flex}
@keyframes paletteIn{from{opacity:0}to{opacity:1}}
.palette__box{width:460px;max-width:90vw;background:var(--surface-raised);border:1px solid var(--border-visible);border-radius:var(--radius-lg);overflow:hidden;animation:paletteBoxIn 140ms var(--ease-out)}
@keyframes paletteBoxIn{from{opacity:0;transform:translateY(-8px) scale(0.98)}to{opacity:1;transform:translateY(0) scale(1)}}
.palette__input{width:100%;background:transparent;border:none;outline:none;font-family:var(--font-mono);font-size:12px;color:var(--text-primary);padding:14px 16px;caret-color:var(--text-display);border-bottom:1px solid var(--border)}
.palette__input::placeholder{color:var(--text-disabled)}
.palette__list{max-height:320px;overflow-y:auto;padding:4px}
.palette__item{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:var(--radius-sm);cursor:pointer;transition:background var(--dur-fast)}
.palette__item:hover,.palette__item--active{background:var(--surface-hover)}
.palette__item-cmd{font-family:var(--font-mono);font-size:11px;color:var(--text-display)}
.palette__item-desc{font-size:10px;color:var(--text-disabled);flex:1;text-align:right}

/* ═══════════ NEW GAME MODAL ═══════════ */
.modal-bg{position:fixed;inset:0;z-index:150;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,0.88)}
.modal-bg--open{display:flex}
.modal{width:420px;max-width:90vw;background:var(--surface-raised);border:1px solid var(--border-visible);border-radius:var(--radius-lg);padding:24px;animation:paletteBoxIn 160ms var(--ease-out)}
.modal__title{font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.14em;color:var(--text-disabled);margin-bottom:20px}
.modal__field{margin-bottom:14px}
.modal__field-label{font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled);margin-bottom:6px;display:block}
.modal__field-input{width:100%;background:var(--surface);border:1px solid var(--border-visible);border-radius:var(--radius-md);padding:8px 12px;font-family:var(--font-mono);font-size:12px;color:var(--text-primary);outline:none;transition:border-color var(--dur-fast)}
.modal__field-input:focus{border-color:var(--text-secondary)}
.modal__toggle{display:flex;align-items:center;gap:10px;margin-bottom:16px;cursor:pointer}
.modal__toggle-track{width:36px;height:20px;border-radius:var(--radius-pill);background:var(--border-visible);position:relative;transition:background var(--dur-fast);flex-shrink:0}
.modal__toggle-track::after{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:var(--text-disabled);transition:all var(--dur-fast)}
.modal__toggle--on .modal__toggle-track{background:var(--text-display)}
.modal__toggle--on .modal__toggle-track::after{transform:translateX(16px);background:var(--black)}
.modal__toggle-label{font-family:var(--font-mono);font-size:10px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.08em}
.modal__actions{display:flex;gap:8px;justify-content:flex-end;margin-top:20px}
.modal__btn{font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.1em;padding:8px 16px;border-radius:var(--radius-pill);cursor:pointer;transition:all var(--dur-fast);border:1px solid var(--border-visible);background:transparent;color:var(--text-secondary)}
.modal__btn:hover{border-color:var(--text-secondary);color:var(--text-primary)}
.modal__btn--primary{background:var(--text-display);color:var(--black);border-color:var(--text-display)}
.modal__btn--primary:hover{opacity:.9}

/* ═══════════ INLINE STATUS ═══════════ */
.istatus{font-family:var(--font-mono);font-size:9px;letter-spacing:0.08em;padding:2px 0;animation:msgIn 100ms var(--ease-out)}
.istatus--ok{color:var(--success)}
.istatus--info{color:var(--interactive)}
.istatus--err{color:var(--accent)}

/* ═══════════ BRANCH INDICATOR ═══════════ */
.branch-tag{display:inline-flex;align-items:center;gap:4px;font-family:var(--font-mono);font-size:9px;letter-spacing:0.08em;color:var(--text-tertiary);text-transform:uppercase;padding:2px 8px;border:1px solid var(--border);border-radius:var(--radius-pill)}
.branch-tag__dot{width:4px;height:4px;border-radius:50%;background:var(--success)}

/* ═══════════ CHARACTER BADGE ═══════════ */
.char-badge{display:flex;align-items:center;gap:6px;padding:6px 0}
.char-badge__name{font-family:var(--font-body);font-size:14px;color:var(--text-display);font-weight:500}
.char-badge__role{font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled)}

/* ═══════════ RESPONSIVE ═══════════ */
@media(max-width:768px){
  :root{--sidebar-w:100vw}
  .topbar{gap:4px;padding:0 10px}
  .topbar__brand{display:none}
  .terminal{padding:12px 14px}
  .msg--hero{font-size:32px}
  .hstat__num{font-size:28px}
  .sidebar__tabs{padding:0 4px}
  .sidebar__tab{padding:0 6px;font-size:7px}
}
</style>
</head>
<body>
<div class="app" id="app">

  <div class="main-area" id="mainArea">
    <!-- TOPBAR -->
    <div class="topbar" id="topbar">
      <div class="topbar__brand"><span>BRING</span> ENGINE</div>
      <div class="topbar__sep"></div>
      <div class="topbar__mem" id="memoryPill" title="Memory Health">
        <span class="topbar__mem-dot" id="memoryDot"></span>
        <span id="memoryPillText">MEM --</span>
      </div>
      <div class="branch-tag" id="branchTag"><span class="branch-tag__dot"></span><span id="branchName">MAIN</span></div>
      <div class="topbar__spacer"></div>
      <span class="topbar__st topbar__st--off" id="apiStatusDot">API</span>
      <span class="topbar__st topbar__st--off" id="wsStatusDot">WS</span>
      <span class="topbar__st topbar__st--off" id="graphStatusDot">GRAPH</span>
      <span class="topbar__clock" id="headerClock">--:--:--</span>
      <button class="topbar__btn" id="newGameBtn"><span class="topbar__btn-dot" style="background:var(--interactive)"></span>NEW</button>
      <button class="topbar__btn" id="toggleSidebarBtn"><span class="topbar__btn-dot"></span>SERVER</button>
    </div>

    <!-- TERMINAL -->
    <div class="terminal" id="terminalOutput"></div>

    <!-- INPUT AREA -->
    <div class="input-area">
      <div class="quick-cmds" id="quickCmds">
        <button class="qcmd" data-cmd="/status">status</button>
        <button class="qcmd" data-cmd="/quests">quests</button>
        <button class="qcmd" data-cmd="/search ">search</button>
        <button class="qcmd" data-cmd="/probability ">prob</button>
        <button class="qcmd" data-cmd="/romance ">romance</button>
        <button class="qcmd" data-cmd="/branch list">branches</button>
        <button class="qcmd" data-cmd="/session list">sessions</button>
        <button class="qcmd" data-cmd="/maintenance quick">maint</button>
        <button class="qcmd" data-cmd="/help">help</button>
      </div>
      <div class="input-area__main">
        <span class="input-area__caret">▸</span>
        <input type="text" class="input-area__field" id="terminalInput" placeholder="type a command or ask anything..." autofocus>
        <div class="input-area__actions">
          <button class="input-area__act" id="paletteBtn" title="Command palette (Ctrl+K)">⌘K</button>
          <button class="input-area__act" id="clearBtn" title="Clear terminal">CLR</button>
        </div>
      </div>
    </div>
  </div>

  <!-- SIDEBAR -->
  <div class="sidebar" id="sidebar">
    <div class="sidebar__tabs" id="sidebarTabs">
      <button class="sidebar__tab sidebar__tab--active" data-tab="world">World</button>
      <button class="sidebar__tab" data-tab="character">Char</button>
      <button class="sidebar__tab" data-tab="quests">Quests</button>
      <button class="sidebar__tab" data-tab="memory">Mem</button>
      <button class="sidebar__tab" data-tab="system">Sys</button>
    </div>
    <div class="sidebar__body" id="sidebarBody">

      <!-- WORLD PANEL -->
      <div class="panel panel--active" id="panelWorld">
        <div class="wcard sb-w" id="wGraphStats">
          <div class="wcard__head"><span class="wcard__title">Graph Overview</span></div>
          <div class="hstat__pair" style="margin-top:10px">
            <div class="hstat"><span class="hstat__num" id="wNodes">--</span><span class="hstat__unit">Nodes</span></div>
            <div class="hstat"><span class="hstat__num" id="wEdges">--</span><span class="hstat__unit">Edges</span></div>
          </div>
        </div>
        <div class="wcard sb-w" id="wIntegrity">
          <div class="wcard__head"><span class="wcard__title">World Integrity</span></div>
          <div class="seg seg--hero" style="margin-top:8px">
            <div class="seg__track" id="wIntTrack"></div>
            <div class="seg__readout"><span class="seg__lbl">Health</span><span class="seg__val" id="wIntVal">--</span></div>
          </div>
        </div>
        <div class="wcard sb-w" id="wBranch">
          <div class="wcard__head"><span class="wcard__title">Active Branch</span></div>
          <div style="margin-top:6px;display:flex;align-items:center;gap:8px">
            <span class="branch-tag"><span class="branch-tag__dot"></span><span id="wBranchName">MAIN</span></span>
            <span style="font-family:var(--font-mono);font-size:9px;color:var(--text-disabled)" id="wBranchCount">1 branch</span>
          </div>
        </div>
        <div class="wcard sb-w" id="wEvents">
          <div class="wcard__head"><span class="wcard__title">Event Feed</span></div>
          <div class="efeed" id="wEventList" style="margin-top:6px">
            <div class="efeed__item"><span class="efeed__time">--:--</span><span class="efeed__text" style="color:var(--text-disabled)">Awaiting events...</span></div>
          </div>
        </div>
      </div>

      <!-- CHARACTER PANEL -->
      <div class="panel" id="panelCharacter">
        <div class="wcard sb-w" id="cCurrent">
          <div class="wcard__head"><span class="wcard__title">Current Character</span></div>
          <div id="cCharInfo" style="margin-top:6px">
            <div style="font-family:var(--font-body);font-size:16px;color:var(--text-disabled)">No character selected</div>
            <div style="font-family:var(--font-mono);font-size:9px;color:var(--text-disabled);letter-spacing:0.08em;margin-top:4px;text-transform:uppercase">Use /romance to set</div>
          </div>
        </div>
        <div class="wcard sb-w" id="cRomance">
          <div class="wcard__head"><span class="wcard__title">Affection</span></div>
          <div class="seg seg--std" style="margin-top:8px">
            <div class="seg__track" id="cAffTrack"></div>
            <div class="seg__readout"><span class="seg__lbl">Level</span><span class="seg__val" id="cAffVal">--</span></div>
          </div>
        </div>
        <div class="wcard sb-w" id="cCompat">
          <div class="wcard__head"><span class="wcard__title">Compatibility</span></div>
          <div class="seg seg--std" style="margin-top:8px">
            <div class="seg__track" id="cCompTrack"></div>
            <div class="seg__readout"><span class="seg__lbl">Score</span><span class="seg__val" id="cCompVal">--</span></div>
          </div>
        </div>
        <div class="wcard sb-w" id="cRels">
          <div class="wcard__head"><span class="wcard__title">Relationships</span></div>
          <div id="cRelList" style="margin-top:6px"><div style="font-size:10px;color:var(--text-disabled)">No data</div></div>
        </div>
        <div class="wcard sb-w" id="cProb">
          <div class="wcard__head"><span class="wcard__title">Probability Trend</span></div>
          <div class="spark" style="margin-top:8px">
            <svg width="90" height="26" viewBox="0 0 90 26"><polyline fill="none" stroke="var(--interactive)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" points="" id="cProbLine"/></svg>
            <span class="spark__val" id="cProbVal">--</span>
          </div>
        </div>
      </div>

      <!-- QUESTS PANEL -->
      <div class="panel" id="panelQuests">
        <div class="wcard sb-w" id="qOverall">
          <div class="wcard__head"><span class="wcard__title">Quest Progress</span></div>
          <div class="seg seg--hero" style="margin-top:8px">
            <div class="seg__track" id="qOverallTrack"></div>
            <div class="seg__readout"><span class="seg__lbl">Complete</span><span class="seg__val" id="qOverallVal">--</span></div>
          </div>
        </div>
        <div id="qListContainer" style="display:flex;flex-direction:column;gap:8px"></div>
      </div>

      <!-- MEMORY PANEL -->
      <div class="panel" id="panelMemory">
        <div class="wcard sb-w" id="mHealth">
          <div class="wcard__head"><span class="wcard__title">Memory Health</span></div>
          <div class="seg seg--hero" style="margin-top:8px">
            <div class="seg__track" id="mHealthTrack"></div>
            <div class="seg__readout"><span class="seg__lbl">Utilization</span><span class="seg__val" id="mHealthVal">--</span></div>
          </div>
        </div>
        <div class="wcard sb-w" id="mDetail">
          <div class="wcard__head"><span class="wcard__title">Breakdown</span></div>
          <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px">
            <div class="srow"><span class="srow__label">Active</span><div class="srow__bar"><div class="seg seg--compact"><div class="seg__track" id="mActTrack"></div></div></div><span class="srow__val" id="mActVal">0</span></div>
            <div class="srow"><span class="srow__label">Faiss</span><div class="srow__bar"><div class="seg seg--compact"><div class="seg__track" id="mFaissTrack"></div></div></div><span class="srow__val" id="mFaissVal">0</span></div>
          </div>
        </div>
        <div class="wcard sb-w" id="mActions">
          <div class="wcard__head"><span class="wcard__title">Maintenance</span></div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
            <button class="qcmd" data-maint="quick">Quick</button>
            <button class="qcmd" data-maint="full">Full</button>
            <button class="qcmd" data-maint="rebuild">Rebuild</button>
            <button class="qcmd" data-maint="clean">Clean</button>
          </div>
        </div>
      </div>

      <!-- SYSTEM PANEL -->
      <div class="panel" id="panelSystem">
        <div class="wcard sb-w" id="sStatus">
          <div class="wcard__head"><span class="wcard__title">Service Status</span></div>
          <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">
            <div class="srow"><span class="srow__label">API</span><span id="sApiStatus" style="font-family:var(--font-mono);font-size:10px;color:var(--text-disabled)">OFFLINE</span></div>
            <div class="srow"><span class="srow__label">WS</span><span id="sWsStatus" style="font-family:var(--font-mono);font-size:10px;color:var(--text-disabled)">OFFLINE</span></div>
            <div class="srow"><span class="srow__label">Graph</span><span id="sGraphStatus" style="font-family:var(--font-mono);font-size:10px;color:var(--text-disabled)">OFFLINE</span></div>
          </div>
        </div>
        <div class="wcard sb-w wcard--expand" id="sTasks">
          <div class="wcard__head"><span class="wcard__title">Active Tasks</span><span class="wcard__chev">▸</span></div>
          <div class="seg seg--std" style="margin-top:8px">
            <div class="seg__track" id="sTaskTrack"></div>
            <div class="seg__readout"><span class="seg__lbl">Progress</span><span class="seg__val" id="sTaskVal">0%</span></div>
          </div>
          <div class="wcard__body"><div class="wcard__body-inner" id="sTaskList"></div></div>
        </div>
        <div class="wcard sb-w wcard--expand" id="sSessions">
          <div class="wcard__head"><span class="wcard__title">Sessions</span><span class="wcard__chev">▸</span></div>
          <div class="wcard__body"><div class="wcard__body-inner" id="sSessionList"><div style="font-size:10px;color:var(--text-disabled)">Loading...</div></div></div>
        </div>
        <div class="wcard sb-w" id="sActions">
          <div class="wcard__head"><span class="wcard__title">Actions</span></div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
            <button class="qcmd" data-cmd="/session list">Sessions</button>
            <button class="qcmd" data-cmd="/branch list">Branches</button>
            <button class="qcmd" data-cmd="/maintenance status">Status</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- COMMAND PALETTE -->
<div class="palette" id="palette">
  <div class="palette__box">
    <input type="text" class="palette__input" id="paletteInput" placeholder="Type a command...">
    <div class="palette__list" id="paletteList"></div>
  </div>
</div>

<!-- NEW GAME MODAL -->
<div class="modal-bg" id="newGameModal">
  <div class="modal">
    <div class="modal__title">◆ New Game Configuration</div>
    <div class="modal__field">
      <label class="modal__field-label">Character Hints</label>
      <input type="text" class="modal__field-input" id="ngHints" placeholder="e.g. noble mage half-elf">
    </div>
    <div class="modal__field">
      <label class="modal__field-label">Starting Age</label>
      <input type="number" class="modal__field-input" id="ngAge" value="5" min="1" max="999">
    </div>
    <div class="modal__toggle" id="ngIsekaiToggle">
      <div class="modal__toggle-track"></div>
      <span class="modal__toggle-label">Isekai / Reincarnation Mode</span>
    </div>
    <div class="modal__actions">
      <button class="modal__btn" id="ngCancel">Cancel</button>
      <button class="modal__btn modal__btn--primary" id="ngLaunch">Launch</button>
    </div>
  </div>
</div>

<script>
(function(){
  // ═══════════════════════════════════════
  //  DOM REFERENCES
  // ═══════════════════════════════════════
  const app = document.getElementById('app');
  const outputEl = document.getElementById('terminalOutput');
  const inputEl = document.getElementById('terminalInput');
  const headerClock = document.getElementById('headerClock');
  const memoryPill = document.getElementById('memoryPill');
  const memoryDot = document.getElementById('memoryDot');
  const memoryPillText = document.getElementById('memoryPillText');
  const apiStatusDot = document.getElementById('apiStatusDot');
  const wsStatusDot = document.getElementById('wsStatusDot');
  const graphStatusDot = document.getElementById('graphStatusDot');
  const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
  const sidebar = document.getElementById('sidebar');
  const sidebarBody = document.getElementById('sidebarBody');
  const branchNameEl = document.getElementById('branchName');
  const palette = document.getElementById('palette');
  const paletteInput = document.getElementById('paletteInput');
  const paletteList = document.getElementById('paletteList');
  const newGameModal = document.getElementById('newGameModal');

  // Sidebar elements
  const wNodes = document.getElementById('wNodes');
  const wEdges = document.getElementById('wEdges');
  const wIntTrack = document.getElementById('wIntTrack');
  const wIntVal = document.getElementById('wIntVal');
  const wBranchName = document.getElementById('wBranchName');
  const wBranchCount = document.getElementById('wBranchCount');
  const wEventList = document.getElementById('wEventList');
  const cCharInfo = document.getElementById('cCharInfo');
  const cAffTrack = document.getElementById('cAffTrack');
  const cAffVal = document.getElementById('cAffVal');
  const cCompTrack = document.getElementById('cCompTrack');
  const cCompVal = document.getElementById('cCompVal');
  const cRelList = document.getElementById('cRelList');
  const cProbLine = document.getElementById('cProbLine');
  const cProbVal = document.getElementById('cProbVal');
  const qOverallTrack = document.getElementById('qOverallTrack');
  const qOverallVal = document.getElementById('qOverallVal');
  const qListContainer = document.getElementById('qListContainer');
  const mHealthTrack = document.getElementById('mHealthTrack');
  const mHealthVal = document.getElementById('mHealthVal');
  const mActTrack = document.getElementById('mActTrack');
  const mActVal = document.getElementById('mActVal');
  const mFaissTrack = document.getElementById('mFaissTrack');
  const mFaissVal = document.getElementById('mFaissVal');
  const sApiStatus = document.getElementById('sApiStatus');
  const sWsStatus = document.getElementById('sWsStatus');
  const sGraphStatus = document.getElementById('sGraphStatus');
  const sTaskTrack = document.getElementById('sTaskTrack');
  const sTaskVal = document.getElementById('sTaskVal');
  const sTaskList = document.getElementById('sTaskList');
  const sSessionList = document.getElementById('sSessionList');

  // ═══════════════════════════════════════
  //  STATE
  // ═══════════════════════════════════════
  let commandHistory = [];
  let historyIndex = -1;
  let sidebarOpen = false;
  let activeTab = 'world';
  let thinkingElement = null;
  let thinkingInterval = null;
  let tasks = [];
  let taskIdCounter = 0;
  let quests = [];
  let chatWs = null;  // WebSocket for /chat/ws endpoint
  let sessions = [];
  let branches = [];
  let currentCharacter = null;
  let currentPartner = null;
  let currentAffection = 0;
  let currentCompatibility = 0;
  let probabilityHistory = [0.42,0.38,0.55,0.61,0.48,0.72,0.68,0.75,0.81,0.77,0.83,0.79,0.86,0.90,0.87];
  let eventFeed = [];
  let graphSummary = { nodes: 0, edges: 0, active_branch: 'main' };
  let isekaiMode = false;
  const API_BASE = '/api';
  const PALETTE_COMMANDS = [
    { cmd: '/status', desc: 'World & memory summary' },
    { cmd: '/search ', desc: 'Search entities' },
    { cmd: '/entity ', desc: 'Entity details' },
    { cmd: '/probability ', desc: 'Check success chance' },
    { cmd: '/romance ', desc: 'Relationship status' },
    { cmd: '/quests', desc: 'List all quests' },
    { cmd: '/quest ', desc: 'Quest details' },
    { cmd: '/branch list', desc: 'List branches' },
    { cmd: '/branch create ', desc: 'Create branch' },
    { cmd: '/branch switch ', desc: 'Switch branch' },
    { cmd: '/session list', desc: 'List sessions' },
    { cmd: '/session history ', desc: 'Session history' },
    { cmd: '/session summarize ', desc: 'Summarize session' },
    { cmd: '/maintenance quick', desc: 'Quick maintenance' },
    { cmd: '/maintenance full', desc: 'Full maintenance' },
    { cmd: '/maintenance rebuild', desc: 'Rebuild FAISS index' },
    { cmd: '/maintenance clean', desc: 'Clean orphans' },
    { cmd: '/memory-forget 30', desc: 'Forget old memories' },
    { cmd: '/memory-summarise general', desc: 'Summarize memories' },
    { cmd: '/clear', desc: 'Clear terminal' },
    { cmd: '/help', desc: 'Show all commands' }
  ];

  // ═══════════════════════════════════════
  //  SEGMENTED PROGRESS BAR RENDERER
  // ═══════════════════════════════════════
  function renderSeg(trackEl, percent, color, count) {
    count = count || 24;
    percent = Math.min(100, Math.max(0, percent));
    const filled = Math.round((percent / 100) * count);
    let html = '';
    for (let i = 0; i < count; i++) {
      if (i < filled) {
        html += '<div class="seg__blk seg__blk--fill" style="background:' + color + ';animation-delay:' + (i * 12) + 'ms"></div>';
      } else {
        html += '<div class="seg__blk seg__blk--empty"></div>';
      }
    }
    trackEl.innerHTML = html;
  }

  // ═══════════════════════════════════════
  //  EVENT FEED
  // ═══════════════════════════════════════
  function addEvent(type, text) {
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
    eventFeed.unshift({ time: time, type: type, text: text });
    if (eventFeed.length > 30) eventFeed.pop();
    renderEventFeed();
  }

  function renderEventFeed() {
    const items = eventFeed.slice(0, 8);
    wEventList.innerHTML = items.map(function(e) {
      return '<div class="efeed__item">' +
        '<span class="efeed__time">' + e.time + '</span>' +
        '<span class="efeed__type efeed__type--' + e.type + '">' + e.type + '</span>' +
        '<span class="efeed__text">' + e.text + '</span></div>';
    }).join('');
  }

  // ═══════════════════════════════════════
  //  DATA LOADERS
  // ═══════════════════════════════════════
  async function loadQuests() {
    try {
      const data = await apiFetch('/quests');
      quests = (data.quests || []).map(function(q) {
        return {
          id: q.id, name: q.title, progress: q.progress || 0,
          subtasks: (q.objectives || []).map(function(obj, idx) {
            return { name: obj.description || 'Objective ' + (idx + 1), done: obj.completed || obj.status === 'completed' || false };
          })
        };
      });
    } catch (e) { quests = []; }
  }

  async function loadSessions() {
    try { sessions = await apiFetch('/sessions') || []; } catch (e) { sessions = []; }
  }

  async function loadBranches() {
    try {
      const data = await apiFetch('/graph/summary');
      branches = data.active_branch ? [data.active_branch] : ['main'];
      graphSummary = data;
    } catch (e) { branches = ['main']; }
  }

  // ═══════════════════════════════════════
  //  TERMINAL OUTPUT HELPERS
  // ═══════════════════════════════════════
  function now() { return new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }); }

  function addMsg(text, cls) {
    cls = cls || '';
    const el = document.createElement('div');
    el.className = 'msg ' + cls;
    el.textContent = text;
    const timeSpan = document.createElement('span');
    timeSpan.className = 'msg__time';
    timeSpan.textContent = now();
    el.appendChild(timeSpan);
    outputEl.appendChild(el);
    scrollTerminal();
    return el;
  }

  function addHTML(html) {
    const wrapper = document.createElement('div');
    const sanitized = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: ['div','span','strong','em','table','thead','tbody','tr','th','td','ul','li','a','br','p','button','svg','circle','polyline','text'],
      ALLOWED_ATTR: ['class','id','style','href','target','colspan','rowspan','data-cmd','d','cx','cy','r','fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','points','transform','viewBox','width','height','font-size','text-anchor','dominant-baseline','letter-spacing'],
      ALLOW_DATA_ATTR: false
    });
    wrapper.innerHTML = sanitized;
    outputEl.appendChild(wrapper);
    scrollTerminal();
    return wrapper;
  }

  function scrollTerminal() { outputEl.scrollTop = outputEl.scrollHeight; }

  async function typeMsg(text, cls, speed) {
    cls = cls || ''; speed = speed || 12;
    return new Promise(function(resolve) {
      const el = document.createElement('div');
      el.className = 'msg ' + cls;
      el.textContent = '';
      outputEl.appendChild(el);
      let i = 0;
      function tick() {
        if (i < text.length) {
          el.textContent += text.charAt(i); i++;
          scrollTerminal();
          setTimeout(tick, Math.random() * speed * 0.4 + speed * 0.7);
        } else { resolve(el); }
      }
      tick();
    });
  }

  function showThinking() {
    if (thinkingElement) removeThinking();
    const el = document.createElement('div');
    el.className = 'thinking';
    el.innerHTML = '<span>[</span><span class="thinking__blks"><span class="thinking__b thinking__b--on"></span><span class="thinking__b"></span><span class="thinking__b"></span><span class="thinking__b"></span></span><span> PROCESSING]</span>';
    outputEl.appendChild(el);
    thinkingElement = el;
    const blocks = el.querySelectorAll('.thinking__b');
    let idx = 0;
    thinkingInterval = setInterval(function() {
      blocks.forEach(function(b) { b.classList.remove('thinking__b--on'); });
      blocks[idx].classList.add('thinking__b--on');
      idx = (idx + 1) % blocks.length;
    }, 160);
    scrollTerminal();
  }

  function removeThinking() {
    if (thinkingInterval) clearInterval(thinkingInterval);
    if (thinkingElement && thinkingElement.parentNode) thinkingElement.remove();
    thinkingElement = null; thinkingInterval = null;
  }

  function addInline(msg, type) {
    type = type || 'info';
    const el = document.createElement('div');
    el.className = 'istatus istatus--' + type;
    el.textContent = '[' + msg.toUpperCase() + ']';
    outputEl.appendChild(el);
    scrollTerminal();
  }

  // ═══════════════════════════════════════
  //  SIDEBAR TABS
  // ═══════════════════════════════════════
  function switchTab(tabName) {
    activeTab = tabName;
    document.querySelectorAll('.sidebar__tab').forEach(function(t) {
      t.classList.toggle('sidebar__tab--active', t.dataset.tab === tabName);
    });
    document.querySelectorAll('.panel').forEach(function(p) {
      p.classList.toggle('panel--active', p.id === 'panel' + tabName.charAt(0).toUpperCase() + tabName.slice(1));
    });
    // Re-trigger stagger
    sidebar.classList.remove('sidebar--visible');
    void sidebar.offsetWidth;
    sidebar.classList.add('sidebar--visible');
  }

  document.getElementById('sidebarTabs').addEventListener('click', function(e) {
    const tab = e.target.closest('.sidebar__tab');
    if (tab && tab.dataset.tab) switchTab(tab.dataset.tab);
  });

  // ═══════════════════════════════════════
  //  SIDEBAR TOGGLE
  // ═══════════════════════════════════════
  function toggleSidebar(force) {
    sidebarOpen = (force !== undefined) ? force : !sidebarOpen;
    if (sidebarOpen) {
      app.classList.add('app--sidebar-open');
      toggleSidebarBtn.classList.add('topbar__btn--active');
      setTimeout(function() { sidebar.classList.add('sidebar--visible'); }, 60);
      refreshAllPanels();
    } else {
      app.classList.remove('app--sidebar-open');
      toggleSidebarBtn.classList.remove('topbar__btn--active');
      sidebar.classList.remove('sidebar--visible');
    }
  }
  toggleSidebarBtn.addEventListener('click', function() { toggleSidebar(); });

  // Expandable cards
  document.addEventListener('click', function(e) {
    const card = e.target.closest('.wcard--expand');
    if (card && !e.target.closest('.seg')) {
      card.classList.toggle('wcard--expanded');
    }
  });

  // ═══════════════════════════════════════
  //  PANEL REFRESH
  // ═══════════════════════════════════════
  function refreshAllPanels() {
    refreshWorldPanel();
    refreshCharPanel();
    refreshQuestPanel();
    refreshMemoryPanel();
    refreshSystemPanel();
  }

  function refreshWorldPanel() {
    wNodes.textContent = graphSummary.nodes || '--';
    wEdges.textContent = graphSummary.edges || '--';
    const total = graphSummary.nodes + graphSummary.edges;
    const integrity = total > 0 ? Math.min(100, Math.round((graphSummary.nodes / Math.max(1, graphSummary.edges)) * 30 + 40 + Math.random() * 20)) : 0;
    renderSeg(wIntTrack, integrity, integrity > 70 ? 'var(--success)' : integrity > 40 ? 'var(--warning)' : 'var(--accent)', 24);
    wIntVal.textContent = integrity + '%';
    wBranchName.textContent = (graphSummary.active_branch || 'main').toUpperCase();
    branchNameEl.textContent = (graphSummary.active_branch || 'main').toUpperCase();
    wBranchCount.textContent = branches.length + ' branch' + (branches.length !== 1 ? 'es' : '');
    renderEventFeed();
  }

  function refreshCharPanel() {
    if (currentCharacter) {
      cCharInfo.innerHTML = '<div class="char-badge"><span class="char-badge__name">' + currentCharacter + '</span></div>';
      renderSeg(cAffTrack, currentAffection * 100, currentAffection > 0.7 ? 'var(--success)' : currentAffection > 0.4 ? 'var(--warning)' : 'var(--accent)', 20);
      cAffVal.textContent = Math.round(currentAffection * 100) + '%';
      renderSeg(cCompTrack, currentCompatibility * 100, 'var(--interactive)', 20);
      cCompVal.textContent = Math.round(currentCompatibility * 100) + '%';
    } else {
      cCharInfo.innerHTML = '<div style="font-family:var(--font-body);font-size:14px;color:var(--text-disabled)">No character selected</div><div style="font-family:var(--font-mono);font-size:9px;color:var(--text-disabled);letter-spacing:0.08em;margin-top:4px;text-transform:uppercase">Use /romance to set</div>';
      renderSeg(cAffTrack, 0, 'var(--accent)', 20); cAffVal.textContent = '--';
      renderSeg(cCompTrack, 0, 'var(--interactive)', 20); cCompVal.textContent = '--';
    }
    // Sparkline
    var pts = probabilityHistory;
    if (pts.length > 1) {
      var maxV = Math.max.apply(null, pts), minV = Math.min.apply(null, pts), range = maxV - minV || 1;
      cProbLine.setAttribute('points', pts.map(function(v, i) {
        return ((i / (pts.length - 1)) * 90).toFixed(1) + ',' + (24 - ((v - minV) / range) * 20).toFixed(1);
      }).join(' '));
      cProbVal.textContent = Math.round(pts[pts.length - 1] * 100) + '%';
    }
    // Relationship list
    if (currentCharacter) {
      fetch('/api/romance/characters/' + encodeURIComponent(currentCharacter))
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var rels = data.relationships || [];
          if (rels.length === 0) { cRelList.innerHTML = '<div style="font-size:10px;color:var(--text-disabled)">No relationships</div>'; return; }
          cRelList.innerHTML = rels.slice(0, 5).map(function(r) {
            var pct = Math.round((r.affection || 0) * 100);
            return '<div class="rel-card">' +
              '<div class="rel-card__names">' + currentCharacter + ' \u21CC ' + (r.partner || '?') + '</div>' +
              '<div class="rel-card__status">' + (r.status || 'unknown') + ' \u00B7 ' + pct + '% affection</div>' +
              '<div class="seg seg--compact" style="margin-top:4px"><div class="seg__track" id="relSeg_' + (r.partner || 'x').replace(new RegExp('\\\\s','g'),'_') + '"></div></div></div>';
          }).join('');
          // Render seg bars after DOM update
          rels.slice(0, 5).forEach(function(r) {
            var el = document.getElementById('relSeg_' + (r.partner || 'x').replace(new RegExp('\\\\s','g'), '_'));
            if (el) renderSeg(el, (r.affection || 0) * 100, (r.affection || 0) > 0.7 ? 'var(--success)' : 'var(--warning)', 16);
          });
        }).catch(function() { cRelList.innerHTML = '<div style="font-size:10px;color:var(--text-disabled)">Unavailable</div>'; });
    } else {
      cRelList.innerHTML = '<div style="font-size:10px;color:var(--text-disabled)">No data</div>';
    }
  }

  function refreshQuestPanel() {
    var totalDone = quests.reduce(function(s, q) { return s + q.subtasks.filter(function(st) { return st.done; }).length; }, 0);
    var totalSubs = quests.reduce(function(s, q) { return s + q.subtasks.length; }, 0);
    var pct = totalSubs > 0 ? (totalDone / totalSubs) * 100 : 0;
    renderSeg(qOverallTrack, pct, 'var(--success)', 24);
    qOverallVal.textContent = Math.round(pct) + '%';
    // Quest cards
    qListContainer.innerHTML = quests.map(function(q, qi) {
      var done = q.subtasks.filter(function(s) { return s.done; }).length;
      var total = q.subtasks.length;
      var qPct = total > 0 ? Math.round((done / total) * 100) : 0;
      return '<div class="wcard sb-w wcard--expand" style="animation-delay:' + (qi * 30) + 'ms">' +
        '<div class="wcard__head"><span class="wcard__title">' + q.name + '</span><span class="wcard__chev">\u25B8</span></div>' +
        '<div class="seg seg--std" style="margin-top:6px"><div class="seg__track" id="qSeg_' + qi + '"></div>' +
        '<div class="seg__readout"><span class="seg__lbl">' + done + '/' + total + '</span><span class="seg__val">' + qPct + '%</span></div></div>' +
        '<div class="wcard__body"><div class="wcard__body-inner">' +
        q.subtasks.map(function(s) {
          return '<div class="stask"><span class="stask__dot ' + (s.done ? 'stask__dot--done' : '') + '"></span><span class="' + (s.done ? 'stask--done' : '') + '">' + s.name + '</span></div>';
        }).join('') +
        '</div></div></div>';
    }).join('');
    // Render quest seg bars
    quests.forEach(function(q, qi) {
      var done = q.subtasks.filter(function(s) { return s.done; }).length;
      var total = q.subtasks.length;
      var qPct = total > 0 ? (done / total) * 100 : 0;
      var el = document.getElementById('qSeg_' + qi);
      if (el) renderSeg(el, qPct, 'var(--success)', 20);
    });
  }

  function refreshMemoryPanel() {
    var active = 0, faiss = 0;
    try {
      apiFetch('/maintenance/status').then(function(memStats) {
        active = (memStats && memStats.memory) ? memStats.memory.total_active_entries : 0;
        faiss = (memStats && memStats.memory) ? memStats.memory.faiss_entries : 0;
        var maxMem = 200, maxFaiss = 300;
        var utilPct = Math.min(100, ((active + faiss) / (maxMem + maxFaiss)) * 100);
        renderSeg(mHealthTrack, utilPct, utilPct > 80 ? 'var(--accent)' : utilPct > 50 ? 'var(--warning)' : 'var(--success)', 24);
        mHealthVal.textContent = Math.round(utilPct) + '%';
        renderSeg(mActTrack, (active / maxMem) * 100, 'var(--success)', 16);
        mActVal.textContent = active;
        renderSeg(mFaissTrack, (faiss / maxFaiss) * 100, 'var(--interactive)', 16);
        mFaissVal.textContent = faiss;
        updateMemoryUI(memStats);
      }).catch(function() {});
    } catch (e) {}
  }

  function refreshSystemPanel() {
    // Status
    sApiStatus.textContent = apiStatusDot.classList.contains('topbar__st--on') ? 'ONLINE' : 'OFFLINE';
    sApiStatus.style.color = apiStatusDot.classList.contains('topbar__st--on') ? 'var(--success)' : 'var(--text-disabled)';
    sWsStatus.textContent = wsStatusDot.classList.contains('topbar__st--on') ? 'ONLINE' : 'OFFLINE';
    sWsStatus.style.color = wsStatusDot.classList.contains('topbar__st--on') ? 'var(--success)' : 'var(--text-disabled)';
    sGraphStatus.textContent = graphStatusDot.classList.contains('topbar__st--on') ? 'ONLINE' : 'OFFLINE';
    sGraphStatus.style.color = graphStatusDot.classList.contains('topbar__st--on') ? 'var(--success)' : 'var(--text-disabled)';
    // Tasks
    var taskDone = tasks.reduce(function(s, t) { return s + t.subtasks.filter(function(st) { return st.status === 'done'; }).length; }, 0);
    var taskTotal = tasks.reduce(function(s, t) { return s + t.subtasks.length; }, 0);
    var taskPct = taskTotal > 0 ? (taskDone / taskTotal) * 100 : 0;
    renderSeg(sTaskTrack, taskPct, 'var(--warning)', 24);
    sTaskVal.textContent = Math.round(taskPct) + '%';
    sTaskList.innerHTML = tasks.length === 0 ? '<div style="font-size:10px;color:var(--text-disabled)">No active tasks</div>' :
      tasks.map(function(t) {
        return '<div style="font-size:11px;color:var(--text-primary);font-weight:500;margin-bottom:2px">' + t.description + '</div>' +
          t.subtasks.map(function(s) {
            return '<div class="stask"><span class="stask__dot ' + (s.status === 'done' ? 'stask__dot--done' : s.status === 'running' ? 'stask__dot--active' : '') + '"></span><span class="' + (s.status === 'done' ? 'stask--done' : '') + '">' + s.description + '</span></div>';
          }).join('');
      }).join('<div style="height:8px"></div>');
    // Sessions
    sSessionList.innerHTML = sessions.length === 0 ? '<div style="font-size:10px;color:var(--text-disabled)">No sessions</div>' :
      sessions.slice(0, 8).map(function(s) {
        var id = s.session_id || s;
        return '<div style="font-family:var(--font-mono);font-size:10px;color:var(--text-secondary);padding:3px 0;border-bottom:1px solid var(--border);cursor:pointer" data-cmd="/session history ' + id + '">' + id + '</div>';
      }).join('');
  }

  // ═══════════════════════════════════════
  //  TASK MANAGEMENT
  // ═══════════════════════════════════════
  function addTask(description, subtaskDescs) {
    subtaskDescs = subtaskDescs || [];
    var id = ++taskIdCounter;
    var task = { id: id, description: description, status: 'pending',
      subtasks: subtaskDescs.map(function(d, idx) { return { id: id + '-' + idx, description: d, status: 'pending' }; })
    };
    tasks.push(task);
    if (sidebarOpen) refreshSystemPanel();
    return task;
  }
  function updateSubtaskStatus(taskId, subtaskIdx, status) {
    var task = tasks.find(function(t) { return t.id === taskId; });
    if (task && task.subtasks[subtaskIdx]) {
      task.subtasks[subtaskIdx].status = status;
      var allDone = task.subtasks.every(function(s) { return s.status === 'done'; });
      var anyRunning = task.subtasks.some(function(s) { return s.status === 'running'; });
      task.status = allDone ? 'done' : anyRunning ? 'running' : 'pending';
      if (sidebarOpen) refreshSystemPanel();
    }
  }
  function updateTaskStatus(taskId, status) {
    var task = tasks.find(function(t) { return t.id === taskId; });
    if (task) task.status = status;
    if (sidebarOpen) refreshSystemPanel();
  }

  // ═══════════════════════════════════════
  //  API
  // ═══════════════════════════════════════
  async function apiFetch(endpoint, options) {
    options = options || {};
    var res = await fetch(API_BASE + endpoint, Object.assign({ headers: { 'Content-Type': 'application/json' } }, options));
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  async function runWithTask(taskDesc, subtasks, fn) {
    var task = addTask(taskDesc, subtasks);
    for (var i = 0; i < subtasks.length; i++) {
      updateSubtaskStatus(task.id, i, 'running');
      addMsg('  [\u25C9] ' + subtasks[i] + ' ...', 'msg--warn');
      try {
        await fn(i);
        updateSubtaskStatus(task.id, i, 'done');
        var last = outputEl.lastElementChild;
        if (last) { last.textContent = '  [\u2713] ' + subtasks[i]; last.className = 'msg msg--success'; }
      } catch (e) {
        updateSubtaskStatus(task.id, i, 'failed');
        addMsg('  [\u2717] ' + subtasks[i] + ' failed: ' + e.message, 'msg--error');
      }
    }
    updateTaskStatus(task.id, 'done');
    addMsg('  [\u2713] Task "' + taskDesc + '" completed.', 'msg--success');
    addEvent('system', 'Task done: ' + taskDesc);
    if (sidebarOpen) refreshAllPanels();
  }

  function updateMemoryUI(memStats) {
    var active = (memStats && memStats.memory) ? memStats.memory.total_active_entries : 0;
    var faiss = (memStats && memStats.memory) ? memStats.memory.faiss_entries : 0;
    memoryPillText.textContent = 'MEM ' + active + ' \u00B7 FAISS ' + faiss;
    memoryDot.className = 'topbar__mem-dot';
    var pct = active / 200 * 100;
    if (pct > 85) memoryDot.classList.add('topbar__mem-dot--crit');
    else if (pct > 60) memoryDot.classList.add('topbar__mem-dot--warn');
  }

  function setStatusDot(el, status) {
    el.className = 'topbar__st';
    el.classList.add('topbar__st--' + status);
  }

  // ═══════════════════════════════════════
  //  COMMAND HANDLERS
  // ═══════════════════════════════════════
  async function cmdStatus() {
    try {
      var summary = await apiFetch('/graph/summary');
      var memStats = await apiFetch('/maintenance/status');
      updateMemoryUI(memStats);
      setStatusDot(graphStatusDot, 'on');
      graphSummary = summary;
      addEvent('system', 'Status check: ' + summary.nodes + ' nodes');
      var html = '<div class="iblock">' +
        '<div class="iblock__label">World Status</div>' +
        '<div class="hstat__pair" style="margin-bottom:16px">' +
        '<div class="hstat"><span class="hstat__num">' + summary.nodes + '</span><span class="hstat__unit">Nodes</span></div>' +
        '<div class="hstat"><span class="hstat__num">' + summary.edges + '</span><span class="hstat__unit">Edges</span></div>' +
        '</div>' +
        '<div class="iblock__grid">' +
        '<div class="iblock__row"><span class="iblock__row-label">Branch</span><span class="iblock__row-value">' + (summary.active_branch || 'main') + '</span></div>' +
        '<div class="iblock__row"><span class="iblock__row-label">Active Mem</span><span class="iblock__row-value">' + (memStats.memory ? memStats.memory.total_active_entries : 0) + '</span></div>' +
        '<div class="iblock__row"><span class="iblock__row-label">Faiss</span><span class="iblock__row-value">' + (memStats.memory ? memStats.memory.faiss_entries : 0) + '</span></div>' +
        '</div></div>';
      addHTML(html);
      if (sidebarOpen) refreshAllPanels();
    } catch (e) {
      addMsg('API error: ' + e.message, 'msg--error');
      setStatusDot(graphStatusDot, 'off');
    }
  }

  async function cmdSearch(query, semantic) {
    semantic = semantic || false;
    showThinking();
    try {
      var res = await apiFetch('/search?q=' + encodeURIComponent(query) + '&semantic=' + semantic + '&top_k=8');
      var results = res.results || [];
      if (!results.length) { addMsg('No results for "' + query + '".', 'msg--dim'); removeThinking(); return; }
      addEvent('entity', 'Search: ' + query + ' (' + results.length + ')');
      var html = '<div class="iblock"><div class="iblock__label">Search: ' + query + '</div>' +
        '<table class="dtable"><thead><tr>' +
        '<th>UID</th><th>Name</th><th>Type</th><th style="text-align:right">Score</th>' +
        '</tr></thead><tbody>';
      results.forEach(function(r) {
        html += '<tr><td class="dtable__mono">' + r.uid + '</td>' +
          '<td><span class="dtable__link" data-cmd="/entity ' + r.uid + '">' + r.name + '</span></td>' +
          '<td>' + r.type + '</td>' +
          '<td class="dtable__mono" style="text-align:right">' + (r.score ? r.score.toFixed(3) : '-') + '</td></tr>';
      });
      html += '</tbody></table></div>';
      addHTML(html);
      if (results[0] && results[0].score) {
        probabilityHistory.push(results[0].score);
        if (probabilityHistory.length > 20) probabilityHistory.shift();
        if (sidebarOpen) refreshCharPanel();
      }
    } catch (e) { addMsg('Search error: ' + e.message, 'msg--error'); }
    removeThinking();
  }

  async function cmdEntity(uid) {
    showThinking();
    try {
      var ent = await apiFetch('/entity/' + encodeURIComponent(uid));
      var neighbors = await apiFetch('/neighbors/' + encodeURIComponent(uid) + '?depth=1&direction=out');
      addEvent('entity', 'Entity: ' + ent.name);
      var html = '<div class="iblock"><div class="iblock__label">Entity: ' + ent.name + '</div>' +
        '<div class="iblock__grid" style="margin-bottom:12px">' +
        '<div class="iblock__row"><span class="iblock__row-label">Type</span><span class="iblock__row-value">' + ent.entity_type + '</span></div>' +
        '<div class="iblock__row"><span class="iblock__row-label">UID</span><span class="iblock__row-value">' + uid + '</span></div>' +
        '</div>' +
        '<div style="font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled);margin-bottom:6px">Layers</div>' +
        '<div class="iblock__grid" style="margin-bottom:12px">' +
        '<div class="iblock__row"><span class="iblock__row-label">L1</span><span class="iblock__row-value" style="font-size:10px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + JSON.stringify(ent.l1).slice(0, 120) + '</span></div>' +
        '<div class="iblock__row"><span class="iblock__row-label">L2</span><span class="iblock__row-value" style="font-size:10px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + JSON.stringify(ent.l2).slice(0, 120) + '</span></div>' +
        '<div class="iblock__row"><span class="iblock__row-label">L3</span><span class="iblock__row-value" style="font-size:10px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + JSON.stringify(ent.l3).slice(0, 120) + '</span></div>' +
        '</div>' +
        '<div style="font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled);margin-bottom:6px">Neighbors (outbound)</div>' +
        (neighbors.map(function(n) {
          return '<div class="iblock__row"><span class="iblock__row-value"><span class="dtable__link" data-cmd="/entity ' + n.name + '">' + n.name + '</span> <span style="color:var(--text-disabled)">(' + n.type + ')</span></span><span style="color:var(--interactive);font-size:10px">' + n.edge_type + '</span></div>';
        }).join('') || '<div style="font-size:10px;color:var(--text-disabled)">None</div>') +
        '</div>';
      addHTML(html);
    } catch (e) { addMsg('Entity error: ' + e.message, 'msg--error'); }
    removeThinking();
  }

  async function cmdProb(profile, actor, target) {
    showThinking();
    try {
      var url = target
        ? '/probability/' + encodeURIComponent(actor) + '/' + encodeURIComponent(profile) + '?target=' + encodeURIComponent(target)
        : '/probability/' + encodeURIComponent(actor) + '/' + encodeURIComponent(profile);
      var data = await apiFetch(url);
      var chance = data.probability || 0;
      addMsg('Probability: ' + actor + ' \u2192 ' + profile + (target ? ' vs ' + target : ''), 'msg--heading');
      addEvent('system', 'Prob: ' + Math.round(chance * 100) + '%');
      probabilityHistory.push(chance);
      if (probabilityHistory.length > 20) probabilityHistory.shift();
      var color = chance > 0.6 ? 'var(--success)' : chance > 0.3 ? 'var(--warning)' : 'var(--accent)';
      var html = '<div class="iblock"><div class="iblock__label">Success Probability</div>' +
        '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px">' +
        '<span style="font-family:var(--font-display);font-size:48px;font-variation-settings:&quot;ROND&quot; 18;font-weight:600;color:' + color + ';letter-spacing:-0.03em;line-height:1">' + Math.round(chance * 100) + '</span>' +
        '<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-disabled)">%</span></div>' +
        '<div class="seg seg--hero"><div class="seg__track" id="probSeg"></div></div></div>';
      addHTML(html);
      var probSegEl = document.getElementById('probSeg');
      if (probSegEl) renderSeg(probSegEl, chance * 100, color, 24);
      if (sidebarOpen) refreshCharPanel();
    } catch (e) { addMsg('Prob error: ' + e.message, 'msg--error'); }
    removeThinking();
  }

  async function cmdRomance(charA, charB) {
    showThinking();
    try {
      var data = await apiFetch('/romance/' + encodeURIComponent(charA) + '/' + encodeURIComponent(charB));
      currentCharacter = charA;
      currentPartner = charB;
      addMsg('Romance: ' + charA + ' \u21CC ' + charB, 'msg--heading');
      addEvent('system', 'Romance: ' + charA + ' \u21CC ' + charB);
      if (data.status && data.status !== 'no_relationship') {
        currentAffection = data.affection || 0;
        currentCompatibility = data.compatibility || 0;
        var html = '<div class="iblock"><div class="iblock__label">Relationship</div>' +
          '<div class="iblock__grid" style="margin-bottom:12px">' +
          '<div class="iblock__row"><span class="iblock__row-label">Status</span><span class="iblock__row-value">' + data.status + '</span></div>' +
          '<div class="iblock__row"><span class="iblock__row-label">Affection</span><span class="iblock__row-value">' + Math.round(currentAffection * 100) + '%</span></div>' +
          '<div class="iblock__row"><span class="iblock__row-label">Compatibility</span><span class="iblock__row-value">' + Math.round(currentCompatibility * 100) + '%</span></div>' +
          '</div>' +
          '<div style="font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled);margin-bottom:6px">Affection</div>' +
          '<div class="seg seg--hero"><div class="seg__track" id="romAffSeg"></div></div>' +
          '<div style="font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-disabled);margin-bottom:6px;margin-top:10px">Compatibility</div>' +
          '<div class="seg seg--std"><div class="seg__track" id="romCompSeg"></div></div></div>';
        addHTML(html);
        var affEl = document.getElementById('romAffSeg');
        var compEl = document.getElementById('romCompSeg');
        if (affEl) renderSeg(affEl, currentAffection * 100, currentAffection > 0.7 ? 'var(--success)' : 'var(--warning)', 24);
        if (compEl) renderSeg(compEl, currentCompatibility * 100, 'var(--interactive)', 24);
      } else {
        addMsg('No relationship found.', 'msg--dim');
        currentAffection = 0; currentCompatibility = 0;
      }
      if (sidebarOpen) { switchTab('character'); refreshCharPanel(); }
    } catch (e) { addMsg('Romance error: ' + e.message, 'msg--error'); }
    removeThinking();
  }

  async function cmdQuest(questId) {
    showThinking();
    try {
      var data = await apiFetch('/quest/' + encodeURIComponent(questId));
      if (data.error) { addMsg('Quest not found: ' + questId, 'msg--error'); }
      else {
        addEvent('system', 'Quest: ' + data.title);
        var html = '<div class="iblock"><div class="iblock__label">Quest: ' + data.title + '</div>' +
          '<div style="font-size:12px;color:var(--text-primary);margin:8px 0">' + (data.description || 'No description') + '</div>' +
          '<div class="iblock__grid" style="margin-bottom:12px">' +
          '<div class="iblock__row"><span class="iblock__row-label">Status</span><span class="iblock__row-value">' + (data.status || 'active') + '</span></div>' +
          '<div class="iblock__row"><span class="iblock__row-label">Progress</span><span class="iblock__row-value">' + (data.progress || 0) + '%</span></div>' +
          '</div>' +
          '<div class="seg seg--std"><div class="seg__track" id="questDetSeg"></div></div></div>';
        addHTML(html);
        var qSegEl = document.getElementById('questDetSeg');
        if (qSegEl) renderSeg(qSegEl, data.progress || 0, 'var(--success)', 24);
        await loadQuests();
        if (sidebarOpen) { switchTab('quests'); refreshQuestPanel(); }
      }
    } catch (e) { addMsg('Quest error: ' + e.message, 'msg--error'); }
    removeThinking();
  }

  async function cmdBranch(action, name) {
    showThinking();
    try {
      if (action === 'create') { await apiFetch('/branch/create?name=' + encodeURIComponent(name), { method: 'POST' }); addMsg('[OK] Created branch: ' + name, 'msg--success'); addEvent('system', 'Branch created: ' + name); }
      else if (action === 'switch') { await apiFetch('/branch/switch?name=' + encodeURIComponent(name), { method: 'POST' }); addMsg('[OK] Switched to: ' + name, 'msg--success'); addEvent('system', 'Switched to: ' + name); }
      else if (action === 'merge') { await apiFetch('/branch/merge?name=' + encodeURIComponent(name), { method: 'POST' }); addMsg('[OK] Merged: ' + name, 'msg--success'); addEvent('system', 'Merged: ' + name); }
      else if (action === 'list') { var s = await apiFetch('/graph/summary'); addMsg('Active branch: ' + (s.active_branch || 'main'), 'msg--dim'); }
      await loadBranches();
      if (sidebarOpen) refreshAllPanels();
    } catch (e) { addMsg('Branch error: ' + e.message, 'msg--error'); }
    removeThinking();
  }

  async function cmdSession(action, sessionId) {
    showThinking();
    try {
      if (action === 'list') {
        var data = await apiFetch('/sessions');
        addEvent('system', 'Sessions: ' + (data.length || 0));
        var html = '<div class="iblock"><div class="iblock__label">Sessions</div>' +
          '<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-secondary);margin-bottom:8px">' + (data.length || 0) + ' sessions</div>' +
          (data.slice(0, 12) || []).map(function(s) {
            var id = s.session_id || s;
            return '<div class="iblock__row"><span class="dtable__link" data-cmd="/session history ' + id + '" style="font-size:10px">' + id + '</span></div>';
          }).join('') + '</div>';
        addHTML(html);
      } else if (action === 'history' && sessionId) {
        var hData = await apiFetch('/sessions/' + encodeURIComponent(sessionId) + '/history');
        addMsg('Session: ' + sessionId + ' \u2014 ' + (hData.turns ? hData.turns.length : 0) + ' turns', 'msg--heading');
        var html = '<div class="iblock"><div class="iblock__label">History</div>' +
          (hData.turns || []).slice(-12).map(function(t) {
            return '<div style="margin-bottom:6px;font-size:10px"><span style="color:var(--interactive);font-family:var(--font-mono);font-size:9px;text-transform:uppercase;letter-spacing:0.06em">' + (t.role || 'user') + '</span> <span style="color:var(--text-primary)">' + (t.content || '').slice(0, 120) + '</span></div>';
          }).join('') + '</div>';
        addHTML(html);
      } else if (action === 'summarize' && sessionId) {
        var sData = await apiFetch('/sessions/' + encodeURIComponent(sessionId) + '/summarize');
        addMsg('Summary: ' + sessionId, 'msg--heading');
        addMsg(sData.summary || 'No summary available', 'msg--dim');
      }
      await loadSessions();
      if (sidebarOpen) refreshSystemPanel();
    } catch (e) { addMsg('Session error: ' + e.message, 'msg--error'); }
    removeThinking();
  }

  async function cmdMaintenance(type) {
    showThinking();
    try {
      if (type === 'full') { await apiFetch('/maintenance/run?full=true', { method: 'POST' }); addMsg('Running full maintenance...', 'msg--heading'); }
      else if (type === 'quick') { await apiFetch('/maintenance/run?full=false', { method: 'POST' }); addMsg('Running quick maintenance...', 'msg--heading'); }
      else if (type === 'rebuild') { await apiFetch('/maintenance/rebuild-index', { method: 'POST' }); addMsg('Rebuilding FAISS index...', 'msg--heading'); }
      else if (type === 'clean') { await apiFetch('/maintenance/clean-orphans', { method: 'POST' }); addMsg('Cleaning orphans...', 'msg--heading'); }
      else if (type === 'status') {
        var ms = await apiFetch('/maintenance/status');
        updateMemoryUI(ms);
        var html = '<div class="iblock"><div class="iblock__label">Maintenance Status</div>' +
          '<div class="iblock__grid">' +
          '<div class="iblock__row"><span class="iblock__row-label">Active Entries</span><span class="iblock__row-value">' + (ms.memory ? ms.memory.total_active_entries : 0) + '</span></div>' +
          '<div class="iblock__row"><span class="iblock__row-label">Faiss Entries</span><span class="iblock__row-value">' + (ms.memory ? ms.memory.faiss_entries : 0) + '</span></div>' +
          '</div></div>';
        addHTML(html);
        removeThinking(); return;
      }
      addEvent('memory', 'Maintenance: ' + type);
      addInline('Maintenance complete', 'ok');
      var memStats = await apiFetch('/maintenance/status');
      updateMemoryUI(memStats);
      if (sidebarOpen) refreshAllPanels();
    } catch (e) { addMsg('Maintenance error: ' + e.message, 'msg--error'); }
    removeThinking();
  }

  async function cmdHelp() {
    var html = '<div class="iblock"><div class="iblock__label">Commands</div>' +
      '<div style="display:grid;grid-template-columns:auto 1fr;gap:3px 20px;font-size:11px">' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/status</span><span style="color:var(--text-secondary)">World & memory overview</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/search &lt;query&gt;</span><span style="color:var(--text-secondary)">Search entities</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/entity &lt;uid&gt;</span><span style="color:var(--text-secondary)">Entity details + neighbors</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/probability &lt;profile&gt; &lt;actor&gt; [target]</span><span style="color:var(--text-secondary)">Success probability</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/romance &lt;A&gt; &lt;B&gt;</span><span style="color:var(--text-secondary)">Relationship status</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/quest &lt;id&gt;</span><span style="color:var(--text-secondary)">Quest details</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/quests</span><span style="color:var(--text-secondary)">List all quests</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/branch &lt;create|switch|merge|list&gt; [name]</span><span style="color:var(--text-secondary)">Branch management</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/session &lt;list|history|summarize&gt; [id]</span><span style="color:var(--text-secondary)">Session management</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/maintenance &lt;full|quick|rebuild|clean|status&gt;</span><span style="color:var(--text-secondary)">Memory maintenance</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/memory-forget &lt;days&gt;</span><span style="color:var(--text-secondary)">Forget old memories</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/memory-summarise &lt;tag&gt;</span><span style="color:var(--text-secondary)">Summarize memories</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/clear</span><span style="color:var(--text-secondary)">Clear terminal</span>' +
      '<span style="color:var(--text-display);font-family:var(--font-mono);font-size:11px">/help</span><span style="color:var(--text-secondary)">Show this help</span>' +
      '</div></div>';
    addHTML(html);
  }

  // ═══════════════════════════════════════
  //  COMMAND DISPATCHER
  // ═══════════════════════════════════════
  async function processInput(raw) {
    var trimmed = raw.trim();
    if (!trimmed) return;
    addMsg('\u25B8 ' + trimmed, 'msg--dim');
    if (trimmed.startsWith('/')) {
      var parts = trimmed.slice(1).split(/\s+/);
      var cmd = parts[0].toLowerCase();
      var args = parts.slice(1);
      switch (cmd) {
        case 'help': await cmdHelp(); break;
        case 'status': await cmdStatus(); break;
        case 'clear': outputEl.innerHTML = ''; break;
        case 'search': await cmdSearch(args.join(' '), false); break;
        case 'entity': if (args[0]) await cmdEntity(args[0]); else addMsg('Usage: /entity <uid>', 'msg--error'); break;
        case 'probability': case 'prob': if (args[0] && args[1]) await cmdProb(args[0], args[1], args[2]); else addMsg('Usage: /probability <profile> <actor> [target]', 'msg--error'); break;
        case 'romance': if (args[0] && args[1]) await cmdRomance(args[0], args[1]); else addMsg('Usage: /romance <A> <B>', 'msg--error'); break;
        case 'quest': case 'quests':
          if (args[0]) { await cmdQuest(args[0]); }
          else {
            try {
              var data = await apiFetch('/quests');
              addEvent('system', 'Quests listed: ' + (data.quests ? data.quests.length : 0));
              var html = '<div class="iblock"><div class="iblock__label">Active Quests (' + (data.quests ? data.quests.length : 0) + ')</div>' +
                (data.quests || []).map(function(q) {
                  return '<div style="margin-top:8px"><div style="font-size:12px;color:var(--text-display);font-weight:500">' + q.title + '</div>' +
                    '<div style="font-size:10px;color:var(--text-secondary);margin-top:2px">' + (q.description || '').slice(0, 80) + '</div>' +
                    '<div style="display:flex;gap:12px;margin-top:4px"><span class="dtable__link" data-cmd="/quest ' + q.id + '" style="font-size:9px">DETAILS</span><span style="font-family:var(--font-mono);font-size:9px;color:var(--text-disabled)">' + (q.progress || 0) + '%</span></div></div>';
                }).join('') + '</div>';
              addHTML(html);
              await loadQuests();
              if (sidebarOpen) { switchTab('quests'); refreshQuestPanel(); }
            } catch (e) { addMsg('Error: ' + e.message, 'msg--error'); }
          }
          break;
        case 'branch': if (args[0]) await cmdBranch(args[0], args[1]); else addMsg('Usage: /branch <create|switch|merge|list> [name]', 'msg--error'); break;
        case 'session': if (args[0]) await cmdSession(args[0], args[1]); else addMsg('Usage: /session <list|history|summarize> [id]', 'msg--error'); break;
        case 'maintenance': if (args[0]) await cmdMaintenance(args[0]); else addMsg('Usage: /maintenance <full|quick|rebuild|clean|status>', 'msg--error'); break;
        case 'memory-maintenance': await cmdMaintenance('full'); break;
        case 'memory-forget':
          try {
            var days = parseInt(args[0]) || 30;
            var fData = await apiFetch('/memory/forget?older_than=' + days + '&min_importance=0.2', { method: 'POST' });
            addMsg('[OK] Forgotten ' + (fData.removed || 0) + ' memories older than ' + days + ' days', 'msg--success');
            addEvent('memory', 'Forgot ' + (fData.removed || 0) + ' memories');
            var ms = await apiFetch('/maintenance/status'); updateMemoryUI(ms);
            if (sidebarOpen) refreshMemoryPanel();
          } catch (e) { addMsg('Error: ' + e.message, 'msg--error'); }
          break;
        case 'memory-summarise':
          try {
            var tag = args[0] || 'general';
            var sData = await apiFetch('/memory/summarise?tag=' + encodeURIComponent(tag), { method: 'POST' });
            addMsg('[OK] Consolidated ' + (sData.consolidated || 0) + ' memories for: ' + tag, 'msg--success');
            addEvent('memory', 'Summarised: ' + tag);
          } catch (e) { addMsg('Error: ' + e.message, 'msg--error'); }
          break;
        default: addMsg('Unknown command: ' + cmd + '. Type /help.', 'msg--error');
      }
    } else {
      // Non-slash messages go to /chat/message for roleplay, not search
      try {
        var resp = await apiFetch('/chat/message', {
          method: 'POST',
          body: JSON.stringify({ content: trimmed })
        });
        if (resp && resp.narrative) {
          addMsg(resp.narrative, 'msg--narrative');
          if (resp.location) addEvent('system', 'Location: ' + resp.location);
        } else if (resp && resp.error) {
          addMsg('[Error] ' + resp.error, 'msg--error');
          // Fall back to search on error
          await cmdSearch(trimmed, true);
        }
      } catch (e) {
        // Fall back to search if chat endpoint unavailable
        await cmdSearch(trimmed, true);
      }
    }
    addMsg('', '');
  }

  // ═══════════════════════════════════════
  //  INPUT HANDLING
  // ═══════════════════════════════════════
  inputEl.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      var val = inputEl.value;
      if (val) {
        commandHistory.push(val);
        if (commandHistory.length > 50) commandHistory.shift();
        historyIndex = commandHistory.length;
        // Route to /chat endpoints - WebSocket first, then REST fallback
        if (chatWs && chatWs.readyState === WebSocket.OPEN) {
          chatWs.send(JSON.stringify({ type: 'message', content: val }));
        } else if (val.startsWith('/')) {
          // Slash commands go to processInput for local handling
          processInput(val);
        } else {
          // Non-command text: send to /chat/message REST endpoint
          apiFetch('/chat/message', {
            method: 'POST',
            body: JSON.stringify({ content: val })
          }).then(function(resp) {
            if (resp && resp.narrative) {
              addMsg(resp.narrative, 'msg--narrative');
              if (resp.location) addEvent('system', 'Location: ' + resp.location);
            } else if (resp && resp.error) {
              addMsg('[Error] ' + resp.error, 'msg--error');
            }
          }).catch(function(err) {
            // Fall back to search if chat fails
            cmdSearch(val, true);
          });
        }
        inputEl.value = '';
      }
      e.preventDefault();
    } else if (e.key === 'ArrowUp') {
      if (historyIndex > 0) { historyIndex--; inputEl.value = commandHistory[historyIndex] || ''; } e.preventDefault();
    } else if (e.key === 'ArrowDown') {
      if (historyIndex < commandHistory.length - 1) { historyIndex++; inputEl.value = commandHistory[historyIndex] || ''; } else { historyIndex = commandHistory.length; inputEl.value = ''; } e.preventDefault();
    }
  });

  // Quick commands
  document.getElementById('quickCmds').addEventListener('click', function(e) {
    var btn = e.target.closest('.qcmd');
    if (btn && btn.dataset.cmd) { inputEl.value = btn.dataset.cmd; inputEl.focus(); }
  });

  // Clear button
  document.getElementById('clearBtn').addEventListener('click', function() { outputEl.innerHTML = ''; });

  // Clickable data-cmd links
  document.addEventListener('click', function(e) {
    var link = e.target.closest('[data-cmd]');
    if (link && link.dataset.cmd) { processInput(link.dataset.cmd); }
  });

  // Focus terminal on click
  document.getElementById('app').addEventListener('click', function(e) {
    if (!e.target.closest('.sidebar') && !e.target.closest('.topbar__btn') && !e.target.closest('button') && !e.target.closest('input') && !e.target.closest('a') && !e.target.closest('.modal') && !e.target.closest('.palette')) {
      inputEl.focus();
    }
  });

  // ═══════════════════════════════════════
  //  COMMAND PALETTE
  // ═══════════════════════════════════════
  function openPalette() {
    palette.classList.add('palette--open');
    paletteInput.value = '';
    paletteInput.focus();
    renderPaletteList('');
  }
  function closePalette() { palette.classList.remove('palette--open'); inputEl.focus(); }

  function renderPaletteList(query) {
    var q = query.toLowerCase();
    var filtered = PALETTE_COMMANDS.filter(function(c) {
      return c.cmd.toLowerCase().indexOf(q) !== -1 || c.desc.toLowerCase().indexOf(q) !== -1;
    });
    paletteList.innerHTML = filtered.map(function(c, i) {
      return '<div class="palette__item' + (i === 0 ? ' palette__item--active' : '') + '" data-pcmd="' + c.cmd + '"><span class="palette__item-cmd">' + c.cmd + '</span><span class="palette__item-desc">' + c.desc + '</span></div>';
    }).join('');
  }

  document.getElementById('paletteBtn').addEventListener('click', openPalette);
  paletteInput.addEventListener('input', function() { renderPaletteList(paletteInput.value); });
  paletteInput.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closePalette(); }
    else if (e.key === 'Enter') {
      var active = paletteList.querySelector('.palette__item--active') || paletteList.querySelector('.palette__item');
      if (active && active.dataset.pcmd) { closePalette(); inputEl.value = active.dataset.pcmd; inputEl.focus(); }
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      var items = paletteList.querySelectorAll('.palette__item');
      var currentIdx = -1;
      items.forEach(function(el, i) { if (el.classList.contains('palette__item--active')) currentIdx = i; });
      items.forEach(function(el) { el.classList.remove('palette__item--active'); });
      var next = e.key === 'ArrowDown' ? Math.min(currentIdx + 1, items.length - 1) : Math.max(currentIdx - 1, 0);
      if (items[next]) { items[next].classList.add('palette__item--active'); items[next].scrollIntoView({ block: 'nearest' }); }
      e.preventDefault();
    }
  });
  paletteList.addEventListener('click', function(e) {
    var item = e.target.closest('.palette__item');
    if (item && item.dataset.pcmd) { closePalette(); inputEl.value = item.dataset.pcmd; inputEl.focus(); }
  });
  palette.addEventListener('click', function(e) { if (e.target === palette) closePalette(); });

  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); palette.classList.contains('palette--open') ? closePalette() : openPalette(); }
    if (e.ctrlKey && e.shiftKey && e.key === 'S') { e.preventDefault(); toggleSidebar(); }
    if (e.key === 'Escape' && sidebarOpen && !palette.classList.contains('palette--open')) { toggleSidebar(false); }
  });

  // ═══════════════════════════════════════
  //  NEW GAME MODAL
  // ═══════════════════════════════════════
  document.getElementById('newGameBtn').addEventListener('click', function() { newGameModal.classList.add('modal-bg--open'); });
  document.getElementById('ngCancel').addEventListener('click', function() { newGameModal.classList.remove('modal-bg--open'); });
  newGameModal.addEventListener('click', function(e) { if (e.target === newGameModal) newGameModal.classList.remove('modal-bg--open'); });

  var isekaiToggle = document.getElementById('ngIsekaiToggle');
  isekaiToggle.addEventListener('click', function() {
    isekaiMode = !isekaiMode;
    isekaiToggle.classList.toggle('modal__toggle--on', isekaiMode);
  });

  document.getElementById('ngLaunch').addEventListener('click', async function() {
    var hints = document.getElementById('ngHints').value || '';
    var startingAge = parseInt(document.getElementById('ngAge').value) || 5;
    newGameModal.classList.remove('modal-bg--open');
    showThinking();
    try {
      var response = await fetch('/api/launch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hints: hints, isekai: isekaiMode, starting_age: startingAge, open_browser: false })
      });
      var data = await response.json();
      removeThinking();
      if (data.status === 'success') {
        addMsg('[OK] New game created', 'msg--success');
        addMsg('[SYS] Starting session: ' + data.character_name, 'msg--success');
        addEvent('system', 'New game launched');
        // Navigate to the session URL to enable roleplay mode
        if (data.url) {
          window.location.href = data.url;
        }
      } else { addMsg('[ERR] ' + (data.error || 'Unknown error'), 'msg--error'); }
    } catch (e) { removeThinking(); addMsg('[ERR] ' + e.message, 'msg--error'); }
  });

  // ═══════════════════════════════════════
  //  MAINTENANCE QUICK ACTIONS
  // ═══════════════════════════════════════
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-maint]');
    if (btn) processInput('/maintenance ' + btn.dataset.maint);
  });

  // ═══════════════════════════════════════
  //  CHAT WEBSOCKET (primary for roleplay)
  // ═══════════════════════════════════════
  var urlParams = new URLSearchParams(window.location.search);
  var sessionId = urlParams.get('session');
  var initialCharacter = urlParams.get('character');

  // Initialize chat session via REST first, then connect WebSocket
  if (initialCharacter) {
    // Setup session via /chat/setup
    apiFetch('/chat/setup', {
      method: 'POST',
      body: JSON.stringify({
        character: initialCharacter,
        location: 'unknown',
        role: 'protagonist',
        session_id: sessionId || 'session_' + Date.now()
      })
    }).then(function(sessionInfo) {
      // Now connect to WebSocket for real-time messaging
      var wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      chatWs = new WebSocket(wsProtocol + '//' + window.location.host + '/chat/ws');

      chatWs.onopen = function() {
        addMsg('[SYS] Connected to chat session', 'msg--success');
        addEvent('system', 'Chat connected: ' + initialCharacter);
        // Send setup message via WebSocket to sync state
        chatWs.send(JSON.stringify({
          type: 'setup',
          character: initialCharacter,
          location: sessionInfo.current_location || 'unknown',
          story_time: sessionInfo.current_time,
          role: 'protagonist',
          session_id: sessionInfo.session_id
        }));
      };

      chatWs.onmessage = function(event) {
        console.log('[CHAT WS] Received:', event.data);
        try {
          var data = JSON.parse(event.data);
          if (data.type === 'narrative') {
            addMsg(data.narrative, 'msg--narrative');
            addEvent('system', 'Narrative update');
          }
          else if (data.type === 'session') {
            // Session confirmed
            addMsg('[SYS] Session active: ' + (data.active_character || initialCharacter), 'msg--dim');
          }
          else if (data.type === 'error') { addMsg('[WS ERROR] ' + data.detail, 'msg--error'); }
          else if (data.type === 'status') { if (sidebarOpen) refreshAllPanels(); }
          else if (data.type === 'pong') { /* keepalive response */ }
          else { console.log('[CHAT WS] Unknown message type:', data.type); }
        } catch (e) { console.error('[CHAT WS] Parse error:', e); }
      };

      chatWs.onerror = function(e) { console.error('[CHAT WS] Error:', e); };
      chatWs.onclose = function() { addMsg('[SYS] Disconnected from chat', 'msg--warn'); addEvent('system', 'Chat disconnected'); };
    }).catch(function(err) {
      console.error('[CHAT] Session setup failed:', err);
      addMsg('[SYS] Chat session setup failed, using REST fallback', 'msg--warn');
    });
  }

  // ═══════════════════════════════════════
  //  MEMORY WEBSOCKET
  // ═══════════════════════════════════════
  var ws = null;
  var wsReconnectTimeout = null;
  function connectWebSocket() {
    try {
      var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(protocol + '//' + window.location.host + '/ws/memory');
      ws.onopen = function() {
        setStatusDot(wsStatusDot, 'on');
        addInline('Memory stream active', 'ok');
        addEvent('system', 'WS connected');
        if (sidebarOpen) refreshSystemPanel();
      };
      ws.onmessage = function(event) {
        try {
          var data = JSON.parse(event.data);
          var msg = data.message || data.event || JSON.stringify(data).slice(0, 100);
          var escaped = msg.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          addMsg('[MEM] ' + escaped, 'msg--system');
          addEvent('memory', msg.slice(0, 50));
          if (sidebarOpen) refreshMemoryPanel();
        } catch (e) {
          var raw = String(event.data).slice(0, 200).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          addMsg('[MEM] ' + raw, 'msg--system');
        }
      };
      ws.onclose = function() { setStatusDot(wsStatusDot, 'warn'); wsReconnectTimeout = setTimeout(connectWebSocket, 5000); };
      ws.onerror = function() { setStatusDot(wsStatusDot, 'off'); };
    } catch (e) { setStatusDot(wsStatusDot, 'off'); wsReconnectTimeout = setTimeout(connectWebSocket, 8000); }
  }

  // ═══════════════════════════════════════
  //  BOOT SEQUENCE
  // ═══════════════════════════════════════
  async function boot() {
    addMsg('', '');
    addMsg('BRING \u00B7 WORLD ENGINE', 'msg--hero');
    addMsg('', '');

    await typeMsg('[KERNEL] Initializing core subsystems...', 'msg--dim', 10);
    await typeMsg('[KERNEL] CPU scheduler online \u00B7 16 threads', 'msg--log', 8);
    await typeMsg('[KERNEL] I/O multiplexer bound to /dev/engine', 'msg--log', 8);
    await typeMsg('[MEMORY] Allocating graph memory pool...', 'msg--dim', 10);
    await typeMsg('[MEMORY] FAISS index placeholder \u00B7 0 entries', 'msg--log', 8);
    await typeMsg('[MEMORY] Consolidation daemon spawned (PID 42)', 'msg--log', 8);
    await typeMsg('[GRAPH] Connecting to graph database...', 'msg--dim', 10);
    await typeMsg('[API] Binding HTTP endpoints on :8000', 'msg--dim', 10);

    try {
      var summary = await apiFetch('/graph/summary');
      setStatusDot(apiStatusDot, 'on');
      setStatusDot(graphStatusDot, 'on');
      graphSummary = summary;
      addMsg('[API] Connected \u00B7 ' + summary.nodes + ' nodes, ' + summary.edges + ' edges', 'msg--success');
      addEvent('system', 'API connected: ' + summary.nodes + ' nodes');
      try {
        var memStats = await apiFetch('/maintenance/status');
        updateMemoryUI(memStats);
        addMsg('[MEMORY] ' + (memStats.memory ? memStats.memory.total_active_entries : 0) + ' active \u00B7 FAISS: ' + (memStats.memory ? memStats.memory.faiss_entries : 0), 'msg--success');
      } catch (e) { addMsg('[MEMORY] Stats unavailable', 'msg--warn'); }
    } catch (e) {
      setStatusDot(apiStatusDot, 'off');
      setStatusDot(graphStatusDot, 'off');
      addMsg('[API] OFFLINE \u2014 ' + e.message, 'msg--error');
      addMsg('[API] Running in degraded mode', 'msg--warn');
      updateMemoryUI({ memory: { total_active_entries: 0, faiss_entries: 0 } });
    }

    await typeMsg('[WS] Establishing memory event stream...', 'msg--dim', 10);
    connectWebSocket();
    await typeMsg('[ENGINE] Probability resolver loaded', 'msg--log', 7);
    await typeMsg('[ENGINE] Romance engine initialized', 'msg--log', 7);
    await typeMsg('[ENGINE] Narrative planner ready', 'msg--log', 7);
    addMsg('', '');
    addMsg('System ready. Type /help or Ctrl+K for commands.', 'msg--dim');
    addMsg('\u2500'.repeat(48), 'msg--dim');
    addMsg('', '');

    try { await loadQuests(); await loadSessions(); await loadBranches(); addMsg('[DATA] Quests loaded', 'msg--log'); addEvent('system', 'Data loaded'); } catch (e) { addMsg('[DATA] Fallback data', 'msg--warn'); }
    await cmdStatus();
    inputEl.focus();
  }

  // ═══════════════════════════════════════
  //  CLOCK
  // ═══════════════════════════════════════
  function updateClock() { headerClock.textContent = new Date().toLocaleTimeString('en-US', { hour12: false }); }
  updateClock(); setInterval(updateClock, 1000);

  // ═══════════════════════════════════════
  //  PERIODIC REFRESH
  // ═══════════════════════════════════════
  setInterval(async function() {
    if (sidebarOpen) {
      try {
        var summary = await apiFetch('/graph/summary');
        graphSummary = summary;
        var memStats = await apiFetch('/maintenance/status');
        updateMemoryUI(memStats);
      } catch (e) {}
      refreshAllPanels();
    }
  }, 12000);

  // ═══════════════════════════════════════
  //  START
  // ═══════════════════════════════════════
  boot();
})();
</script>
</body>
</html>
"""
