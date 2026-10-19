# 行业知识问答

有色行业和钢铁行业的知识练习系统。打开浏览器访问 http://127.0.0.1:8000 。

当前 MongoDB 和 Django 都已停止。按下面的顺序重新启动。

## 启动

在项目目录 `D:\schneider\知识问答` 打开两个 PowerShell 窗口。

第一个窗口启动 MongoDB，这个窗口要一直开着：

```powershell
cd D:\schneider\知识问答
.\start_mongo.ps1
```

看到日志里出现 `Waiting for connections` 后，在第二个窗口启动网页：

```powershell
cd D:\schneider\知识问答
python manage.py runserver 127.0.0.1:8000
```

浏览器打开 http://127.0.0.1:8000 。题库和向量已经导入过，日常启动不用再跑导入命令。

## 停止

在两个窗口里分别按 `Ctrl+C`。先停 Django，再停 MongoDB。

## 第一次准备

换一台电脑，或本机还没有依赖时，先做这些步骤，然后再按上面的方式启动。

1. 使用已安装 PyTorch 的 Python（本机是 Anaconda 的 Python 3.13）。安装依赖：

```powershell
python -m pip install -r requirements.txt
```

2. 项目根目录需要有 `.env`。不要把这个文件提交到 git。内容如下，把密钥换成自己的：

```text
DJANGO_DEBUG=1
DEEPSEEK_BASE_URL=https://api-inference.modelscope.cn/v1
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_MODEL=deepseek-ai/DeepSeek-V4.1-Flash-1017
MONGO_URI=mongodb://127.0.0.1:27017
MONGO_DB_NAME=knowledge_qa
MONGO_COLLECTION=answer_vectors
EMBEDDING_MODEL=shibing624/text2vec-base-chinese
HF_ENDPOINT=https://hf-mirror.com
SCORE_SIMILARITY_WEIGHT=0.4
SCORE_LLM_WEIGHT=0.6
```

3. 向量模型文件放在 `.models\text2vec-base-chinese`。本机已经下载好，换机器时需要把这个目录一起拷过去。

4. MongoDB 可执行文件在 `.tools\mongodb\...\bin\mongod.exe`。`start_mongo.ps1` 会自己找到它，数据目录是 `.mongo-data`。

5. 先按上一节启动 MongoDB，再初始化数据库并导入题库：

```powershell
python manage.py migrate
python manage.py ingest_knowledge
python manage.py runserver 127.0.0.1:8000
```

CSV 或向量模型更换后，再执行一次 `python manage.py ingest_knowledge`。
