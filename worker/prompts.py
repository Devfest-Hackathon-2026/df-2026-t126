"""プロンプト（shared-types.md §8）。文言はここだけで管理する。"""
from pydantic import BaseModel


class Prompts(BaseModel):
    image_from_odai: str = (
        "次のお題の場面を、1枚の絵にしてください。お題: 「{odai}」。"
        "動作や様子がはっきり分かるように描き、文字は入れないでください。"
    )
    image_from_text: str = "次の説明の絵を、シンプルな1枚の絵として描いてください。文字は入れないでください。説明: {text}"
    image_from_empty: str = "何かを自由に思いついた、シンプルで少し不思議な1枚の絵を描いてください。文字は入れないでください。"
    gesture_read: str = (
        "次は、手の21点の座標を時系列で並べたデータです（x,y,zは0〜1、mirroredが真なら左右反転）。"
        "この手の動きは、何かを身振りで伝えようとしています。何を表しているか、1〜2文の日本語で説明してください。"
    )
    conclude: str = (
        "この絵は、何をしているところですか。「〜している〇〇」の形で、日本語の短い1文で答えてください"
        "（例:「走っているきりん」「歌っているカエル」）。"
        "品種や固有名詞、背景の細かい説明は避け、いちばん目立つ動作と主役だけを答えてください。"
    )


PROMPTS = Prompts()


def build_image_prompt(text: str, p: Prompts = PROMPTS) -> str:
    """文章が空・空白のみなら、空用のプロンプトを返す。"""
    if not text or not text.strip():
        return p.image_from_empty
    return p.image_from_text.format(text=text.strip())


def build_first_image_prompt(odai: str, p: Prompts = PROMPTS) -> str:
    return p.image_from_odai.format(odai=odai)
