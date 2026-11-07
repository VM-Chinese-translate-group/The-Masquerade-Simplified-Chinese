import json
import os
import re
from pathlib import Path
from typing import Tuple
import requests

TOKEN: str = os.getenv("API_TOKEN", "")
GH_TOKEN: str = os.getenv("GH_TOKEN", "")
PROJECT_ID: str = os.getenv("PROJECT_ID", "")
FILE_URL: str = f"https://paratranz.cn/api/projects/{PROJECT_ID}/files/" if PROJECT_ID else ""

# 初始化列表和字典
file_id_list: list[int] = []
file_path_list: list[str] = []
zh_cn_list: list[dict[str, str]] = []


def fetch_json(url: str, headers: dict[str, str]):
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def translate(file_id: int) -> Tuple[list[str], list[str]]:
    """
    获取指定文件的翻译内容并返回键值对列表

    :param file_id: 文件ID
    :return: 包含键和值的元组列表
    """
    url = f"https://paratranz.cn/api/projects/{PROJECT_ID}/files/{file_id}/translation"
    headers = {"Authorization": TOKEN, "accept": "*/*"}
    translations = fetch_json(url, headers)

    keys, values = [], []

    for item in translations:
        keys.append(item["key"])
        translation = item.get("translation", "")
        original = item.get("original", "")
        # 优先使用翻译内容，缺失时根据 stage 使用原文
        values.append(
            original if item["stage"] in [0, -1, 2] or not translation else translation
        )

    return keys, values


def get_files() -> None:
    """
    获取项目中的文件列表并提取文件ID和路径
    """
    headers = {"Authorization": TOKEN, "accept": "*/*"}
    files = fetch_json(FILE_URL, headers)

    for file in files:
        file_id_list.append(file["id"])
        file_path_list.append(file["name"])


def resolve_paths(cloud_name: str) -> Tuple[Path, Path]:
    """
    解析云端文件对应的本地源文件路径(Source)与输出资源包路径(CNPack)。
    固定规则：
      云端 en_us.json 对应本地源文件 Source/assets/test/lang/en_us.json
      重定向输出至 CNPack/assets/vm/lang/zh_cn.json
    """
    if cloud_name == "en_us.json":
        source_path = Path("Source/assets/test/lang/en_us.json")
        target_path = Path("CNPack/assets/vm/lang/zh_cn.json")
        return source_path, target_path

    # 通用后备规则（未来如增加其他文件）
    # 重定向 assets/test -> assets/vm
    rel_path = Path(cloud_name)
    source_path = Path("Source") / rel_path
    if not source_path.exists():
        alt_source = Path("Source") / str(rel_path).replace("assets/vm", "assets/test")
        if alt_source.exists():
            source_path = alt_source

    target_str = str(rel_path).replace("en_us.json", "zh_cn.json").replace("assets/test", "assets/vm")
    target_path = Path("CNPack") / target_str
    return source_path, target_path


def process_translation(file_id: int) -> dict[str, str]:
    """
    处理单个文件的翻译，返回翻译字典

    :param file_id: 文件ID
    :return: 翻译内容字典
    """
    keys, values = translate(file_id)
    zh_cn_dict = {}

    for key, value in zip(keys, values):
        # 确保替换 \\ 和 \n
        value = re.sub(r'\\\\', r'\\', value)
        value = re.sub(r'\\n', '\n', value)

        # 仅当值包含中文字符时，才将常规空格替换为不间断空格
        if re.search(r'[\u4e00-\u9fff]', value):
            value = re.sub(' ', '\u00A0', value)

        zh_cn_dict[key] = value

    return zh_cn_dict


def save_translation(zh_cn_dict: dict[str, str], source_path: Path, target_path: Path) -> None:
    """
    保存翻译内容到目标 JSON 文件，并利用源文件保持键排序与修复 Paratranz 255字符截断。

    :param zh_cn_dict: 从 Paratranz 获取的翻译内容字典
    :param source_path: 对应的本地源文件路径 (Source)
    :param target_path: 输出资源包文件路径 (CNPack)
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "w", encoding="UTF-8") as f:
        try:
            with open(source_path, "r", encoding="UTF-8") as f1:
                source_json: dict = json.load(f1)

            # --- 核心键匹配与截断修复逻辑 ---
            corrected_zh_cn_dict = {}
            unmatched_paratranz_keys = []

            for pt_key, pt_value in zh_cn_dict.items():
                if pt_key in source_json:
                    corrected_zh_cn_dict[pt_key] = pt_value
                else:
                    unmatched_paratranz_keys.append(pt_key)

            # 处理被 Paratranz 截断的键（长度为 255 字符）
            source_keys_set = set(source_json.keys())
            for pt_key in unmatched_paratranz_keys:
                found_match = False
                if len(pt_key) == 255:
                    for source_key in source_keys_set:
                        if source_key.startswith(pt_key):
                            corrected_zh_cn_dict[source_key] = zh_cn_dict[pt_key]
                            found_match = True
                            break

                if not found_match:
                    print(f"警告: Paratranz 的键 '{pt_key[:50]}...' 在源文件中未匹配，该条将被忽略。")

            # 按照源文件的键顺序构建最终 JSON 对象；未翻译的键回退使用原文
            final_json_object = {}
            for source_key in source_json.keys():
                final_json_object[source_key] = corrected_zh_cn_dict.get(source_key, source_json[source_key])

            json.dump(final_json_object, f, ensure_ascii=False, indent=4, separators=(",", ":"))

        except IOError:
            print(f"源文件 {source_path} 路径不存在，文件将按首字母排序输出！")
            sorted_dict = {key: zh_cn_dict[key] for key in sorted(zh_cn_dict.keys())}
            json.dump(sorted_dict, f, ensure_ascii=False, indent=4, separators=(",", ":"))


def main() -> None:
    if not TOKEN or not PROJECT_ID:
        raise EnvironmentError("环境变量 API_TOKEN 或 PROJECT_ID 未设置。")
    get_files()
    for file_id, path_name in zip(file_id_list, file_path_list):
        if "TM" in path_name:  # 跳过 TM 临时/对照文件
            continue
        zh_cn_dict = process_translation(file_id)
        zh_cn_list.append(zh_cn_dict)

        source_path, target_path = resolve_paths(path_name)
        save_translation(zh_cn_dict, source_path, target_path)
        print(f"已从 Paratranz 同步翻译并保存至：{target_path}（参考源文件：{source_path}）")


if __name__ == "__main__":
    main()
