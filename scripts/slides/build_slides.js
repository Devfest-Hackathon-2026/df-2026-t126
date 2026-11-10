// プレゼンスライド（現地会場・4分）を、pptx で作る。Google ドライブに上げて「Google スライドで開く」で変換する。
// 内容: 提出するプロダクト説明ドキュメント（プロダクト説明ドキュメント_VQX）の流れに合わせる。
//       課題 → ゲームの流れ → デモ → 新しいところ → Google Cloud → AI と安全性 → まとめ
// デザイン: 本番サイトに合わせる（docs/slide-design-notes.md）。ベージュの背景、太い黒の枠、右下にずらした黒い影、
//           5色（ベージュ・黒・青・ピンク・オレンジ）、いちばん太い見出し、サイトの人のミニキャラ。書体は Noto Sans JP のみ。
// 1枚目は、サイトの最初の画面（StartScreen）と同じ構成。
// 使い方: NODE_PATH=<pptxgenjs と sharp がある node_modules> node scripts/slides/build_slides.js
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..", "..");
const FIG = path.join(ROOT, "docs", "submission", "slides", "figures");
const ARCH = path.join(ROOT, "docs", "submission", "architecture.png");
const OUT = path.join(ROOT, "docs", "submission", "slides", "プレゼンスライド_VQX.pptx");
const sizes = JSON.parse(fs.readFileSync(path.join(FIG, "sizes.json"), "utf-8"));

const C = { bg: "EFE2D9", ink: "1B1B1B", blue: "1E58EE", pink: "FCB4C0", orange: "FF5936", soft: "E3D7CE", paper: "FFFFFF", muted: "6B6560" };
const PINK_TEXT = "E8788F"; // ピンクの文字用（背景が白でも読める濃さ）
const FONT = "Noto Sans JP";
const SHADOW = 0.055; // 右下にずらす量（インチ）
const LINE = 2.25; // 枠の太さ（pt）

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.title = "プレゼンスライド_VQX";
pres.author = "VQX";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
pres.defineSlideMaster({ title: "BASE", background: { color: C.bg } });

// ---- 部品（サイトの見た目: 太い黒の枠 + ずらした黒い影）----
function card(slide, name, x, y, w, h, fill = C.paper, radius = 0.14) {
  slide.addShape(pres.ShapeType.roundRect, { x: x + SHADOW, y: y + SHADOW, w, h, rectRadius: radius, fill: { color: C.ink }, line: { color: C.ink, width: LINE }, objectName: `${name} 影` });
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: radius, fill: { color: fill }, line: { color: C.ink, width: LINE }, objectName: name });
}

function pill(slide, label, x, y, w, fill = C.blue, color = C.paper) {
  const h = 0.3;
  card(slide, `タグ ${label}`, x, y, w, h, fill, h / 2);
  slide.addText(label, { x, y, w, h, align: "center", valign: "middle", fontFace: FONT, fontSize: 10.5, bold: true, color, charSpacing: 3, margin: 0, isTextBox: true, objectName: `タグの文字 ${label}` });
}

function title(slide, text, tag, tagFill, tagColor) {
  pill(slide, tag, 0.5, 0.42, 0.28 + tag.length * 0.105, tagFill, tagColor);
  slide.addText(text, { x: 0.5, y: 0.82, w: 9, h: 0.8, fontFace: FONT, fontSize: 34, bold: true, color: C.ink, margin: 0, valign: "top", isTextBox: true, objectName: "見出し" });
}

function fig(slide, name, x, y, h, flip = false) {
  const r = sizes[name].ratio;
  slide.addImage({ path: path.join(FIG, `${name}.png`), x, y, w: h * r, h, flipH: flip, altText: "サイトのミニキャラ（人・ロボット）" });
  return h * r;
}

/** 足元をそろえて、横に並べる（重なりは、少しだけ） */
function row(slide, names, x0, baseY, h, gap = -0.15) {
  let x = x0;
  for (const name of names) {
    const w = fig(slide, name, x, baseY - h, h);
    x += w + gap;
  }
  return x - gap - x0;
}

// ============================================================
// 1. タイトル（10秒）— サイトの最初の画面と同じ構成
// ============================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  // 左: GESTURE RELAY / ジェスチャー / 伝言（大きく）/ 一言
  s.addText("GESTURE RELAY", { x: 0.55, y: 0.78, w: 3.2, h: 0.28, fontFace: FONT, fontSize: 11, bold: true, color: C.blue, charSpacing: 5, margin: 0, isTextBox: true, objectName: "小さい英語の見出し" });
  s.addText("ジェスチャー", { x: 0.55, y: 1.08, w: 4.6, h: 0.5, fontFace: FONT, fontSize: 26, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true, objectName: "サブ見出し" });
  s.addText([
    { text: "伝", options: { color: C.ink } },
    { text: "言", options: { color: C.orange } },
  ], { x: 0.45, y: 1.45, w: 4.8, h: 2.1, fontFace: FONT, fontSize: 108, bold: true, margin: 0, valign: "middle", isTextBox: true, objectName: "伝言（大）" });
  s.addText("3人で遊ぶ、伝言ゲーム。", { x: 0.55, y: 3.65, w: 4.6, h: 0.32, fontFace: FONT, fontSize: 14, color: C.muted, margin: 0, valign: "middle", isTextBox: true, objectName: "リード 1" });
  s.addText("言葉と動きで、お題を伝える。", { x: 0.55, y: 3.98, w: 4.9, h: 0.48, fontFace: FONT, fontSize: 21, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true, objectName: "リード 2" });
  s.addText("チーム VQX ｜ DevFest GDGoC Japan Hackathon 2026（大阪）", { x: 0.55, y: 5.22, w: 8, h: 0.28, fontFace: FONT, fontSize: 10.5, color: C.muted, margin: 0, isTextBox: true, objectName: "チーム名" });
  // 右: ジェスチャーをする青い人と、首をかしげるピンクの人、「？」
  fig(s, "a_gesture", 5.45, 1.0, 2.75);
  fig(s, "b_think", 7.95, 1.55, 2.2);
  s.addText("？", { x: 8.5, y: 0.75, w: 0.8, h: 0.95, fontFace: FONT, fontSize: 48, bold: true, color: C.orange, margin: 0, align: "center", valign: "middle", isTextBox: true, objectName: "？（大）" });
  s.addText("？", { x: 9.2, y: 0.55, w: 0.5, h: 0.5, fontFace: FONT, fontSize: 24, bold: true, color: C.orange, margin: 0, align: "center", valign: "middle", isTextBox: true, objectName: "？（小）" });
  // 下: 3つの STEP（サイトと同じ）
  const chips = [
    { dot: C.blue, step: "STEP 1", t: "人A：絵を文章に" },
    { dot: C.pink, step: "STEP 2", t: "人B：身ぶりで伝える" },
    { dot: C.orange, step: "STEP 3", t: "人C：録画を文章に" },
  ];
  chips.forEach((c, i) => {
    const w = 1.42, h = 0.78, x = 5.2 + i * (w + 0.1), y = 4.32;
    s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.1, fill: { color: C.soft }, line: { color: C.soft, width: 0.5 }, objectName: `STEP${i + 1}の枠` });
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.12, y: y + 0.1, w: 0.11, h: 0.11, fill: { color: c.dot }, line: { color: c.dot, width: 0.5 }, objectName: `STEP${i + 1}の点` });
    s.addText(c.step, { x: x + 0.28, y: y + 0.06, w: w - 0.35, h: 0.2, fontFace: FONT, fontSize: 9, bold: true, color: C.blue, charSpacing: 2, margin: 0, valign: "middle", isTextBox: true, objectName: `STEP${i + 1}の英語` });
    s.addText(c.t, { x: x + 0.1, y: y + 0.3, w: w - 0.12, h: 0.44, fontFace: FONT, fontSize: 9, bold: true, color: C.ink, margin: 0, valign: "top", isTextBox: true, objectName: `STEP${i + 1}の文` });
  });
  s.addNotes("【10秒】チームVQXです。「ジェスチャー伝言」は、言葉と動きで、お題を伝える、3人の伝言ゲームです。");
}

// ============================================================
// 2. 課題（30秒）— ドキュメントの「課題と根拠」
// ============================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  title(s, "伝わらない、もどかしさ", "WHY", C.blue, C.paper);
  card(s, "課題のカード", 0.5, 1.75, 4.75, 3.1);
  s.addText("私たちの出発点", { x: 0.8, y: 2.0, w: 3.5, h: 0.3, fontFace: FONT, fontSize: 12, bold: true, color: C.blue, charSpacing: 3, margin: 0, isTextBox: true, objectName: "出発点の見出し" });
  s.addText([
    { text: "心が動いたことを、", options: { breakLine: true } },
    { text: "自分の言葉で", options: { breakLine: true } },
    { text: "人に伝えられない。" },
  ], { x: 0.8, y: 2.4, w: 3.3, h: 1.4, fontFace: FONT, fontSize: 22, bold: true, color: C.ink, margin: 0, valign: "top", lineSpacingMultiple: 1.2, isTextBox: true, objectName: "課題の文" });
  s.addText("ライブの後も、\n「すごかった」しか出てこない。", { x: 0.8, y: 3.95, w: 3.1, h: 0.7, fontFace: FONT, fontSize: 14, color: C.muted, margin: 0, valign: "top", isTextBox: true, objectName: "具体例" });
  fig(s, "c_think", 4.2, 3.05, 1.65);
  // 右: 2つの数字
  const stats = [
    { n: "43.3%", c: C.orange, t: "「自分の考えを、はっきり\n伝えられない」と答えた人（15〜39歳）" },
    { n: "45.0%", c: C.blue, t: "SNSで「相手の感情が\n分かりにくい」と感じる人" },
  ];
  stats.forEach((st, i) => {
    const y = 1.75 + i * 1.6, x = 5.55, w = 3.95, h = 1.45;
    card(s, `数字${i + 1}`, x, y, w, h);
    s.addText(st.n, { x: x + 0.25, y: y + 0.12, w: w - 0.5, h: 0.7, fontFace: FONT, fontSize: 40, bold: true, color: st.c, margin: 0, valign: "middle", isTextBox: true, objectName: `数字${i + 1}の数` });
    s.addText(st.t, { x: x + 0.25, y: y + 0.85, w: w - 0.45, h: 0.5, fontFace: FONT, fontSize: 12, color: C.ink, margin: 0, valign: "top", isTextBox: true, objectName: `数字${i + 1}の文` });
  });
  s.addText("出典: 内閣府（2022年）、文化庁（2025年）の調査", { x: 5.55, y: 4.98, w: 4, h: 0.25, fontFace: FONT, fontSize: 10, color: C.muted, margin: 0, isTextBox: true, objectName: "出典" });
  s.addNotes("【30秒】出発点は、感動したことを、自分の言葉で、うまく伝えられないもどかしさです。国の調査でも、自分の考えをはっきり伝えられない人は43.3%、SNSで相手の感情が分かりにくいと感じる人は45.0%でした。言葉にして、伝わったかを確かめることを繰り返せば、伝える力は伸ばせる。でも1人では続かないので、友だちと笑いながら繰り返せる、ゲームにしました。");
}

// ============================================================
// 3. ゲームの流れ（25秒）
// ============================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  title(s, "ゲームの流れ", "HOW TO PLAY", C.pink, C.ink);
  const steps = [
    { n: "1", text: "AI が絵を描く", color: C.ink, fig: "r_draw", figH: 0.8 },
    { n: "2", text: "人A が文にする", color: C.blue, fig: "a_stand" },
    { n: "3", text: "人B が手で伝える", color: PINK_TEXT, fig: "b_gesture" },
    { n: "4", text: "人C が文にする", color: C.orange, fig: "c_think" },
    { n: "5", text: "AI が絵を描きなおす", color: C.ink, fig: "r_redraw", figH: 0.8 },
    { n: "6", text: "AI がお題を当てる", color: C.ink, fig: "r_answer", figH: 0.85 },
  ];
  const cw = 2.833, ch = 1.55, gap = 0.25;
  steps.forEach((st, i) => {
    const col = i % 3, row2 = Math.floor(i / 3);
    const x = 0.5 + col * (cw + gap), y = 1.75 + row2 * (ch + 0.22);
    card(s, `手順${st.n}`, x, y, cw, ch);
    s.addText(st.n, { x: x + 0.25, y: y + 0.12, w: 0.9, h: 0.85, fontFace: FONT, fontSize: 44, bold: true, color: st.color, margin: 0, valign: "top", isTextBox: true, objectName: `手順${st.n}の数字` });
    s.addText(st.text, { x: x + 0.25, y: y + 1.0, w: cw - 0.4, h: 0.4, fontFace: FONT, fontSize: 16, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true, objectName: `手順${st.n}の文` });
    if (st.fig) {
      const h = st.figH || 0.78, r = sizes[st.fig].ratio;
      fig(s, st.fig, x + cw - 0.3 - h * r, y + 0.1, h);
    }
  });
  s.addNotes("【25秒】遊び方は、3人が、それぞれのスマホやパソコンから、4桁のコードで同じ部屋に入ります。1、AI がお題の絵を描きます。2、人A が、その絵を文章にします。3、人B が、その文章を、身ぶりで伝えます。4、人C が、その録画を見て、また文章にします。5、AI が、その文章から絵を描きなおし、6、最後に、お題を当てにきます。");
}

// ============================================================
// 4. デモ（約80秒）
// ============================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  title(s, "デモ", "DEMO", C.orange, C.paper);
  card(s, "動画の枠", 0.5, 1.55, 6.5, 3.66);
  s.addText("ここに、デモ動画（MP4）を埋め込む", { x: 0.5, y: 1.55, w: 6.5, h: 3.66, align: "center", valign: "middle", fontFace: FONT, fontSize: 18, bold: true, color: C.muted, margin: 0, isTextBox: true, objectName: "動画の枠の文字（動画を置いたら消す）" });
  row(s, ["a_wave", "b_gesture"], 7.3, 5.21, 2.2, -0.1);
  s.addNotes("【約80秒】ここで、デモ動画を流す。\n※スライドに動画を埋め込む手順: Google スライドで、挿入 → 動画 → Google ドライブ → 提出フォルダの MP4 を選ぶ。枠のサイズを合わせ、この文字（「ここに、…」）は消す。\n※MP4 の本体も、提出フォルダに入れる。両方とも、再生できることを確認する（運営の指定）。\n話すこと: 本物のサーバーで、3人が遊んでいる様子です。人B の手の動きに、光る線が重なり、それを録画します。最後に、AI が、お題との近さを、「近い！」「おしい！」「遠い…」で見せます。");
}

// ============================================================
// 5. 新しいところ（25秒）— ドキュメントの「既存手法との違い」
// ============================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  title(s, "ここが、新しい", "WHAT'S NEW", C.pink, C.ink);
  const cards = [
    { n: "1", t: "伝え方が、変わる", d: "絵→言葉→体→言葉→絵", c: C.blue },
    { n: "2", t: "どこで途切れたか", d: "全部の段を、見返せる", c: PINK_TEXT },
    { n: "3", t: "人と AI を比べる", d: "「AI には\nこう見えました」", c: C.orange },
  ];
  const cw = 2.833;
  cards.forEach((cd, i) => {
    const x = 0.5 + i * (cw + 0.25), y = 1.8;
    card(s, `新しい点${cd.n}`, x, y, cw, 2.5);
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.28, y: y + 0.28, w: 0.62, h: 0.62, fill: { color: cd.c }, line: { color: C.ink, width: LINE }, objectName: `丸${cd.n}` });
    s.addText(cd.n, { x: x + 0.28, y: y + 0.28, w: 0.62, h: 0.62, align: "center", valign: "middle", fontFace: FONT, fontSize: 22, bold: true, color: i === 0 ? C.paper : C.ink, margin: 0, isTextBox: true, objectName: `丸${cd.n}の数字` });
    s.addText(cd.t, { x: x + 0.28, y: y + 1.1, w: cw - 0.5, h: 0.55, fontFace: FONT, fontSize: 18, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true, objectName: `新しい点${cd.n}の見出し` });
    s.addText(cd.d, { x: x + 0.28, y: y + 1.68, w: cw - 0.5, h: 0.65, fontFace: FONT, fontSize: 14, color: C.ink, margin: 0, valign: "top", isTextBox: true, objectName: `新しい点${cd.n}の文` });
  });
  s.addText("これまでの伝言ゲームは、言葉と絵だけ。体は使いません。", { x: 0.5, y: 4.65, w: 9, h: 0.4, fontFace: FONT, fontSize: 14, color: C.muted, margin: 0, isTextBox: true, objectName: "既存との違い" });
  s.addNotes("【25秒】新しいところは3つです。1、絵、言葉、体、言葉、絵と、伝え方を変えながら、3人でつなぎます。2、全部の段を見返せるので、どこで伝わらなくなったかが見えます。3、AI が手の動きを読み取り、「AI にはこう見えました」と見せるので、人の解釈と AI の解釈を比べられます。似た作品は、言葉と絵だけで、体を使いません。");
}

// ============================================================
// 6. Google Cloud（25秒）
// ============================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  title(s, "Google Cloud で動いています", "GOOGLE CLOUD", C.blue, C.paper);
  card(s, "構成図の枠", 0.5, 1.7, 5.75, 3.55);
  const ih = 3.3, iw = ih * (3440 / 2320);
  s.addImage({ path: ARCH, x: 0.5 + (5.75 - iw) / 2, y: 1.7 + (3.55 - ih) / 2, w: iw, h: ih, altText: "システム構成図（Google Cloud）" });
  const items = [
    { t: "Cloud Run", d: "3つに分けて動かす", c: C.blue },
    { t: "Vertex AI（Gemini）", d: "鍵を置かず、AI を呼ぶ", c: PINK_TEXT },
    { t: "Firestore", d: "3人の画面を同期する", c: C.orange },
  ];
  items.forEach((it, i) => {
    const y = 1.7 + i * 1.2, x = 6.55, w = 2.95, h = 1.05;
    card(s, `要点${i + 1}`, x, y, w, h);
    s.addText(it.t, { x: x + 0.2, y: y + 0.12, w: w - 0.35, h: 0.4, fontFace: FONT, fontSize: 16, bold: true, color: it.c, margin: 0, valign: "middle", isTextBox: true, objectName: `要点${i + 1}の見出し` });
    s.addText(it.d, { x: x + 0.2, y: y + 0.55, w: w - 0.35, h: 0.38, fontFace: FONT, fontSize: 14, color: C.ink, margin: 0, valign: "middle", isTextBox: true, objectName: `要点${i + 1}の文` });
  });
  s.addNotes("【25秒】実行は、すべて Google Cloud です。画面は Firebase Hosting、サーバーは Cloud Run を、API、AI の処理、期限処理の3つに分けています。AI は Vertex AI の Gemini で、鍵をコードに置かず、Google Cloud の認証で呼びます。Firestore で、3人の画面をリアルタイムに合わせ、Cloud Tasks と Cloud Scheduler で、時間のかかる処理や、止まった処理を、自動で進めます。");
}

// ============================================================
// 7. AI の使い方と安全性（25秒）
// ============================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  title(s, "AI の使い方と、安全性", "AI × SAFETY", C.orange, C.paper);
  const cards = [
    { n: "1", t: "手の座標だけ", d: "映像は AI に送らない", c: C.blue },
    { n: "2", t: "鍵を置かない", d: "Google Cloud の認証で AI を呼ぶ", c: PINK_TEXT },
    { n: "3", t: "止まらない", d: "失敗しても、やり直す", c: C.orange },
  ];
  const cw = 2.833;
  cards.forEach((cd, i) => {
    const x = 0.5 + i * (cw + 0.25), y = 1.8;
    card(s, `カード${cd.n}`, x, y, cw, 2.55);
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.28, y: y + 0.28, w: 0.62, h: 0.62, fill: { color: cd.c }, line: { color: C.ink, width: LINE }, objectName: `丸${cd.n}` });
    s.addText(cd.n, { x: x + 0.28, y: y + 0.28, w: 0.62, h: 0.62, align: "center", valign: "middle", fontFace: FONT, fontSize: 22, bold: true, color: i === 0 ? C.paper : C.ink, margin: 0, isTextBox: true, objectName: `丸${cd.n}の数字` });
    s.addText(cd.t, { x: x + 0.28, y: y + 1.1, w: cw - 0.5, h: 0.5, fontFace: FONT, fontSize: 20, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true, objectName: `カード${cd.n}の見出し` });
    s.addText(cd.d, { x: x + 0.28, y: y + 1.62, w: cw - 0.5, h: 0.7, fontFace: FONT, fontSize: 14, color: C.ink, margin: 0, valign: "top", isTextBox: true, objectName: `カード${cd.n}の文` });
  });
  s.addText("AI の出番: 絵を描く／手を読む／お題を当てる／近さを測る", { x: 0.5, y: 4.65, w: 9, h: 0.4, fontFace: FONT, fontSize: 14, color: C.muted, margin: 0, isTextBox: true, objectName: "AI の出番" });
  s.addNotes("【25秒】AI は4か所で使っています。絵を描く、手の動きを読む、お題を当てる、近さを数値にする、です。顔が写る映像は AI に送らず、端末の中で取り出した、手の座標だけを渡します。鍵はどこにも置かず、失敗しても、自動でやり直して、ゲームが止まりにくい作りにしています。");
}

// ============================================================
// 8. まとめと今後（10秒）
// ============================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  title(s, "まとめ", "THANK YOU", C.pink, C.ink);
  const lines = [
    { t: "笑いながら、伝わりを振り返る", c: C.blue },
    { t: "Google Cloud で、安定して動く", c: PINK_TEXT },
    { t: "今後: 4人以上、エフェクトも増やす", c: C.orange },
  ];
  lines.forEach((ln, i) => {
    const y = 1.95 + i * 0.85;
    s.addShape(pres.ShapeType.ellipse, { x: 0.5, y: y + 0.08, w: 0.3, h: 0.3, fill: { color: ln.c }, line: { color: C.ink, width: LINE }, objectName: `点${i + 1}` });
    s.addText(ln.t, { x: 1.0, y, w: 5.3, h: 0.5, fontFace: FONT, fontSize: 20, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true, objectName: `まとめの文${i + 1}` });
  });
  s.addText("ありがとうございました", { x: 0.5, y: 4.55, w: 6, h: 0.5, fontFace: FONT, fontSize: 24, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true, objectName: "ありがとう" });
  row(s, ["a_wave", "b_surprised", "c_laugh"], 6.5, 4.95, 2.1, -0.12);
  s.addNotes("【10秒】まとめです。言葉と動きで伝えて、笑いながら、どこで伝わらなくなったかを振り返れます。Google Cloud で、安定して動いています。今後は、4人以上で遊べるようにし、光る線のエフェクトも増やします。ありがとうございました。");
}

pres.writeFile({ fileName: OUT }).then((f) => console.log("作成:", f));
