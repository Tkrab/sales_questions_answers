# 行业知识问答

有色行业和钢铁行业的知识练习系统。学员选择题目作答后，由模型对照标准答案和评分要点打分，并可以在学习中心查看自己的记录。

## 启动

本地部署时需要先启动 MongoDB，网页服务依赖它读取题库向量。

在项目目录打开两个终端。

第一个终端启动 MongoDB，这个窗口要一直开着：

```powershell
.\start_mongo.ps1
```

看到日志里出现 `Waiting for connections` 后，在第二个终端启动网页：

```powershell
python manage.py runserver
```

题库和向量已经导入过时，日常启动不用再跑导入命令。

## 停止

在两个终端里分别按 `Ctrl+C`。先停 Django，再停 MongoDB。

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
