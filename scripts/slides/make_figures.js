// スライド用に、サイトの人のミニキャラ（ぷっくりした棒人間）を、PNG に書き出す。
// 姿勢の座標は frontend/src/ui/pose.ts、線の太さ・影は frontend/src/ui/figure.ts と同じ。
// 使い方: node scripts/slides/make_figures.js <出力フォルダ>   （sharp が必要）
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const INK = "#1B1B1B";
const COLORS = { blue: "#1E58EE", pink: "#FCB4C0", orange: "#FF5936" };

const LEFT_LEG = [[-6, -22], [-8, 0]];
const RIGHT_LEG = [[6, -22], [8, 0]];
const P = (h, n, p, a, b, l, r) => ({ h, n, p, a, b, l, r });
// pose.ts の POSES から、スライドで使う姿勢だけを写した
const POSES = {
  stand: P([0, -90], [0, -76], [0, -42], [[-10, -60], [-12, -44]], [[10, -60], [12, -44]], LEFT_LEG, RIGHT_LEG),
  wave: P([0, -90], [0, -76], [0, -42], [[-10, -60], [-12, -44]], [[18, -82], [24, -102]], LEFT_LEG, RIGHT_LEG),
  gesture1: P([0, -90], [0, -76], [2, -42], [[-18, -90], [-8, -110]], [[20, -72], [38, -84]], [[-12, -22], [-20, 0]], [[14, -22], [20, 0]]),
  gesture3: P([0, -91], [0, -77], [0, -42], [[-24, -90], [-6, -108]], [[24, -90], [6, -108]], [[-12, -22], [-18, 0]], [[12, -22], [18, 0]]),
  think: P([5, -89], [0, -76], [0, -42], [[-12, -58], [2, -52]], [[14, -62], [8, -82]], LEFT_LEG, RIGHT_LEG),
  clap1: P([-4, -89], [-2, -76], [1, -42], [[-12, -62], [2, -72]], [[14, -62], [4, -74]], LEFT_LEG, RIGHT_LEG),
  laugh1: P([-8, -88], [-4, -75], [2, -42], [[-20, -90], [-26, -106]], [[12, -92], [22, -108]], [[-8, -22], [-12, 0]], [[10, -22], [14, 0]]),
  surprised: P([0, -93], [0, -79], [0, -44], [[-18, -84], [-26, -100]], [[18, -84], [26, -100]], [[-10, -22], [-14, 0]], [[10, -22], [14, 0]]),
  walkA: P([0, -90], [0, -76], [0, -42], [[-8, -60], [-15, -47]], [[8, -60], [15, -47]], [[-5, -21], [-13, 0]], [[5, -21], [13, 0]]),
};

const f = (p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`;

function figureSvg(pose, color, arcs = false) {
  const q = pose;
  // サイトの最初の画面と同じ、手のまわりの「ふるえ」の弧（オレンジ）
  const [lx, ly] = q.a[1];
  const [rx, ry] = q.b[1];
  const arcSvg = arcs
    ? `<path d="M${lx - 7} ${ly - 7}q-5 7 0 14M${lx - 12} ${ly - 12}q-9 12 0 24M${rx + 7} ${ry - 7}q5 7 0 14M${rx + 12} ${ry - 12}q9 12 0 24" fill="none" stroke="#FF5936" stroke-width="2.6" stroke-linecap="round" opacity="0.7"/>`
    : "";
  const d =
    `M${f(q.n)}L${f(q.p)}` +
    `M${f(q.n)}L${f(q.a[0])}L${f(q.a[1])}` +
    `M${f(q.n)}L${f(q.b[0])}L${f(q.b[1])}` +
    `M${f(q.p)}L${f(q.l[0])}L${f(q.l[1])}` +
    `M${f(q.p)}L${f(q.r[0])}L${f(q.r[1])}`;
  const stroke = (c, w) => `<path d="${d}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  const head = (c, r) => `<circle cx="${q.h[0]}" cy="${q.h[1]}" r="${r}" fill="${c}"/>`;
  // 右下にずらした影 → 黒い縁 → 色
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-62 -132 124 148" width="496" height="592">` +
    arcSvg +
    `<g transform="translate(4 4)">${stroke(INK, 19)}${head(INK, 14)}</g>` +
    `${stroke(INK, 19)}${head(INK, 14)}${stroke(color, 13)}${head(color, 11)}` +
    `</svg>`
  );
}

// ---- ロボット（サイトの frontend/src/ui/scenes.ts の robot() と同じ作り）----
const ROBOT = "#CDBDF0";
const PAPER = "#FFFFFF";

/** ロボット本体。座標は scenes.ts と同じ（足元 y=124）。dx で横にずらす */
function robotBody(dx = 0) {
  const shapes = [[30, 112, 8, 12, 2], [44, 112, 8, 12, 2], [26, 74, 30, 40, 6], [22, 44, 38, 28, 8]];
  const shadow = shapes.map(([x, y, w, h, rx]) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${INK}"/>`).join("");
  const body = shapes.map(([x, y, w, h, rx]) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${ROBOT}" stroke="${INK}" stroke-width="3"/>`).join("");
  return (
    `<g transform="translate(${dx} 0)">` +
    `<g transform="translate(4 4)">${shadow}</g>${body}` +
    `<line x1="41" y1="44" x2="41" y2="34" stroke="${INK}" stroke-width="3"/>` +
    `<circle cx="41" cy="32" r="4.5" fill="#FF5936"/>` +
    `<circle cx="33" cy="57" r="3.5" fill="${INK}"/><circle cx="49" cy="57" r="3.5" fill="${INK}"/>` +
    `<path d="M35 64q6 5 12 0" fill="none" stroke="${INK}" stroke-width="2.5" stroke-linecap="round"/>`
  );
}

/** 絵を描くロボット（draw: 青、redraw: オレンジの線で、ペンの腕の角度を変える）。AI が絵を描く段階 */
function robotDrawSvg(variant) {
  const line = variant === "redraw" ? "#FF5936" : "#1E58EE";
  const rot = variant === "redraw" ? -10 : 8;
  const easel =
    `<path d="M118 124L130 40M178 124L166 40" stroke="${INK}" stroke-width="3" stroke-linecap="round" fill="none"/>` +
    `<rect x="112" y="30" width="72" height="58" rx="3" fill="${PAPER}" stroke="${INK}" stroke-width="2.5"/>` +
    `<path d="M134 72c-8 0-8-14 2-14c-6-10 12-14 14-4c10-2 12 12 2 14c4 8-10 12-14 6c-2 0-4-1-4-2z" fill="none" stroke="${line}" stroke-width="2.5" stroke-linecap="round"/>`;
  const arm =
    `<g transform="rotate(${rot} 56 86)"><path d="M56 86L76 80" stroke="${INK}" stroke-width="6" stroke-linecap="round" fill="none"/>` +
    `<path d="M76 80l8-10" stroke="#FF5936" stroke-width="3" stroke-linecap="round" fill="none"/></g>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="12 22 184 112" width="1472" height="896">${easel}${robotBody(30).replace(/<g transform="translate\(30 0\)">/, '<g transform="translate(30 0)">')}${arm}</g></svg>`;
}

/** 答えのカードを掲げるロボット（お題を当てる段階）。サイトの laughScene と同じカード */
function robotAnswerSvg() {
  const card =
    `<path d="M56 86L66 80" stroke="${INK}" stroke-width="6" stroke-linecap="round" fill="none"/>` +
    `<g transform="rotate(-6 84 74)"><rect x="62" y="54" width="46" height="38" rx="3" fill="${PAPER}" stroke="${INK}" stroke-width="2.5"/>` +
    `<circle cx="82" cy="80" r="8" fill="none" stroke="${INK}" stroke-width="2"/><circle cx="82" cy="66" r="5" fill="none" stroke="${INK}" stroke-width="2"/>` +
    `<path d="M87 65l6 2-6 2z" fill="#FF5936"/></g>`;
  const mark = `<text x="112" y="46" font-family="Hiragino Sans, Arial" font-weight="900" font-size="30" fill="#FF5936" text-anchor="middle">！</text>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="12 14 112 120" width="896" height="960">${robotBody(0)}${card}</g>${mark}</svg>`;
}

async function main() {
  const out = process.argv[2];
  if (!out) throw new Error("出力フォルダを指定してください");
  fs.mkdirSync(out, { recursive: true });
  const jobs = [
    ["a_gesture", "gesture1", COLORS.blue, true],
    ["b_think", "think", COLORS.pink],
    ["a_wave", "wave", COLORS.blue],
    ["a_stand", "stand", COLORS.blue],
    ["b_gesture", "gesture1", COLORS.pink],
    ["b_gesture3", "gesture3", COLORS.pink],
    ["c_think", "think", COLORS.orange],
    ["c_clap", "clap1", COLORS.orange],
    ["c_laugh", "laugh1", COLORS.orange],
    ["b_surprised", "surprised", COLORS.pink],
    ["a_walk", "walkA", COLORS.blue],
  ];
  const sizes = {};
  for (const [name, pose, color, arcs] of jobs) {
    const svg = figureSvg(POSES[pose], color, !!arcs);
    fs.writeFileSync(path.join(out, `${name}.svg`), svg);
    // 余白を切り詰めて、配置しやすくする（縦横比は、出力の sizes.json に残す）
    const file = path.join(out, `${name}.png`);
    const buf = await sharp(Buffer.from(svg), { density: 300 }).png().trim().toBuffer();
    fs.writeFileSync(file, buf);
    const meta = await sharp(buf).metadata();
    sizes[name] = { w: meta.width, h: meta.height, ratio: meta.width / meta.height };
  }
  // ロボット（AI の段階用）
  const robots = [
    ["r_draw", robotDrawSvg("draw")],
    ["r_redraw", robotDrawSvg("redraw")],
    ["r_answer", robotAnswerSvg()],
  ];
  for (const [name, svg] of robots) {
    fs.writeFileSync(path.join(out, `${name}.svg`), svg);
    const buf = await sharp(Buffer.from(svg), { density: 300 }).png().trim().toBuffer();
    fs.writeFileSync(path.join(out, `${name}.png`), buf);
    const meta = await sharp(buf).metadata();
    sizes[name] = { w: meta.width, h: meta.height, ratio: meta.width / meta.height };
  }
  fs.writeFileSync(path.join(out, "sizes.json"), JSON.stringify(sizes, null, 2));
  console.log("人のミニキャラとロボットを書き出しました:", jobs.length + robots.length, "枚 →", out);
}

main();
