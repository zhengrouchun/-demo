# 解决学习任务迁移时SQLite备份文件被占用的问题

日期：2026-10-03。项目：LocalLecture / GrowMate。

## 问题及原因

为学习任务新增数据库表时，需要先备份已有 growmate.db。迁移测试虽然写完备份，但临时目录清理报 Windows WinError32，表示备份数据库文件仍被进程占用。

原实现使用：

~~~python
with sqlite3.connect(backup) as target:
    repo.db.backup(target)
~~~

sqlite3.Connection 的上下文管理器处理事务提交/回滚，退出 with 时不保证关闭连接。Windows 文件句柄持续占用，临时目录不能安全移除。测试旧库夹具也存在相同的连接关闭问题。

## 阅读文件与应用位置

- `app/backend/meetingbro/growmate/task_support.py`：migrate() 在修改表结构前的 SQLite backup 调用。
- `tests/test_learning_tasks.py`：test_old_database_migration_baseline_backup_and_reopen 的旧数据库准备、备份检查和临时目录回收。
- `app/backend/meetingbro/growmate/repository.py`：Repository 的连接生命周期、transaction() 和 close()，用于确认仓库连接本身已正常释放。

## 解决流程及方法

1. 从迁移测试错误定位到备份文件句柄，没有删除或强制移动用户数据库。
2. 检查 connect 上下文语义，区分事务结束与连接关闭。
3. 使用 contextlib.closing 显式关闭目标备份连接：

~~~python
from contextlib import closing

with closing(sqlite3.connect(backup)) as target:
    repo.db.backup(target)
~~~

4. 测试夹具同样用 closing，并显式 commit 旧数据准备事务；仓库测试结束继续调用 repo.close()。
5. 重跑 12 项学习任务测试，验证备份存在、原内容保留、重开不重复迁移和临时目录正常回收。
6. 正式加载后，检查旧行数量/内容指纹一致，正式库和备份 PRAGMA integrity_check 均为 ok。

## 使用指令及结果

从 `D:\语音转文字工具\LocalLecture` 执行：

~~~powershell
& '.\app\backend\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_learning_tasks.py' -q
~~~

结果：Ran 12 tests / OK，文件占用问题消失。

相关只读数据库检查：

~~~sql
PRAGMA table_info(focus_sessions);
PRAGMA integrity_check;
SELECT name, applied_at FROM schema_migrations;
~~~

本次正式备份为：
`data/growmate/growmate.before-learning-tasks-20261003-165343-d030b7.db`。

后续迁移或导出工具若使用 sqlite3.connect 的上下文，应分别处理事务和连接生命周期；需要关闭文件句柄时用 closing 或显式 close。

