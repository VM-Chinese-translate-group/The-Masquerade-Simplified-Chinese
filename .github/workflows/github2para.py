import asyncio
import os
import json
from pprint import pprint
import paratranz_client
from pydantic import ValidationError

configuration = paratranz_client.Configuration(host="https://paratranz.cn/api")
configuration.api_key["Token"] = os.environ.get("API_TOKEN", "")


async def upload_file(path, file):
    async with paratranz_client.ApiClient(configuration) as api_client:
        api_instance = paratranz_client.FilesApi(api_client)
        project_id = int(os.environ["PROJECT_ID"])
        files_response = await api_instance.get_files(project_id)
        file_base_name = os.path.basename(file)

        # 优先匹配已有文件进行更新，避免重复创建
        for fileName in files_response:
            if fileName.name == file_base_name:
                await api_instance.update_file(project_id, file_id=fileName.id, file=file)
                print(f"文件已更新！文件名：{fileName.name} (ID: {fileName.id})")
                return

        try:
            # 第一次创建文件
            api_response = await api_instance.create_file(
                project_id, file=file, path=path
            )
            pprint(api_response)
            print(f"文件上传成功：{path}{file_base_name}")
        except ValidationError:
            print(f"文件上传完成：{path}{file_base_name}")
        except Exception as e:
            try:
                error_body = json.loads(e.__dict__.get("body", "{}"))
                filePath: str = error_body.get("message", "").split(" ")[1]
            except Exception:
                filePath = file_base_name

            for fileName in files_response:
                if fileName.name == filePath or fileName.name == file_base_name:
                    await api_instance.update_file(project_id, file_id=fileName.id, file=file)
                    print(f"文件已更新！文件名：{fileName.name} (ID: {fileName.id})")
                    return
            raise e


def get_filelist(dir):
    filelist = []
    for root, _, files in os.walk(dir):
        for file in files:
            if "en_us" in file and file.endswith(".json"):
                filelist.append(os.path.join(root, file))
    return filelist


async def main():
    files = get_filelist("./Source")
    tasks = []

    for file in files:
        # 当为 Source/assets/test/lang/en_us.json 时，上传至 Paratranz 根目录以对应现存 en_us.json
        if os.path.basename(file) == "en_us.json":
            path = ""
        else:
            path = (
                file.split("Source")[1]
                .replace("\\", "/")
                .replace(os.path.basename(file), "")
            )
        print(f"Uploading {file} to path='{path}'")
        tasks.append(upload_file(path=path, file=file))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
