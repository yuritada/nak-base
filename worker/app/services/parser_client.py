"""
Parser Service Client
- ファイルパスを渡してテキスト抽出を依頼
"""
import requests
from ..config import get_settings

settings = get_settings()


def call_parser(file_path: str) -> dict:
    """
    Parserサービスを呼び出してテキスト抽出

    Args:
        file_path (str): 解析対象のファイルパス (共有ボリューム上のパス)

    Returns:
        dict: パース結果
            {
                "text": "全文テキスト",
                "meta": {メタデータ},
                "pages": [ページごとの情報],
                "chunks": [チャンクごとの情報]
            }
    
    Raises:
        requests.exceptions.RequestException: APIコールに失敗した場合
        ValueError: レスポンスの形式が不正な場合
    """
    try:
        response = requests.post(
            f"{settings.parser_url}/parse",
            json={"file_path": file_path},
            timeout=120
        )
        response.raise_for_status()
        result = response.json()

        # レスポンス形式の検証
        if "content" in result:
            # 新しい形式
            return {
                "text": result["content"],
                "meta": result.get("meta", {}),
                "pages": result.get("pages", []),
                "chunks": result.get("chunks", [])
            }
        elif "text" in result:
            # 古い形式（後方互換性）
            return {
                "text": result["text"],
                "meta": {},
                "pages": [],
                "chunks": []
            }
        else:
            raise ValueError("Parser response is missing 'content' or 'text' field.")

    except requests.exceptions.RequestException as e:
        print(f"Parser service request failed: {e}")
        raise
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Failed to parse response from Parser service: {e}")
        raise

