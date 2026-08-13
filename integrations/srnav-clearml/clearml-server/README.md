# SR-Nav local ClearML Server

This is the first-phase, no-Agent deployment for the reusable observability
template. It keeps the ClearML Web UI, REST API and Fileserver on loopback:

| Channel | Local value |
| --- | --- |
| Web UI | `http://127.0.0.1:8080` |
| REST API | `http://127.0.0.1:8008` |
| Fileserver | `http://127.0.0.1:8081` |
| SDK config | `clearml.conf` |
| Artifact output URI | `http://127.0.0.1:8081` |

`8080` 由本地统一 gateway 提供：ClearML Web 上游监听 `8082`，Research Hub
挂载在 `/research/`。启动完整入口请使用：

```bash
./start_unified_ui.sh
```

随后直接打开 `http://127.0.0.1:8080/research/`（不需要手工复制 token；统一
gateway 在服务端注入 Hub session token）。ClearML Web 根地址仍是
`http://127.0.0.1:8080/`；单实验校阅地址形如：
`http://127.0.0.1:8080/research/experiments/<run_id>`。

The default artifact destination is the ClearML Fileserver. Raw datasets and
checkpoints remain excluded by the project profile; only explicitly selected
scorecards, receipts, manifests and review media are uploaded.

## Start and inspect

```bash
./start_local_server.sh
docker compose -f docker-compose.yml ps
```

`start_local_server.sh` 只启动 ClearML 后端；需要同一个网址时，再运行
`start_unified_ui.sh`（它会复用已经启动的容器）。

The compose file deliberately does not define `clearml-agent-services`, so it
cannot pull a task from a queue or start GPU work. `state/` is local runtime
state and is ignored by Git.

## Optional SSH access

When the server runs on a remote host, execute this from the client:

```bash
./ssh_tunnel.sh user@remote-host
```

The tunnel exposes the same three local ports and does not make the server
public. No SSH host, user, key, or ClearML credential is committed here.
