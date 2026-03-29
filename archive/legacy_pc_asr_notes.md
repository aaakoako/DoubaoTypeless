## Retired PC Direct-ASR Scheme

这个方案已经退出主线，只保留复盘信息。

### 原方案链路

1. PC 全局热键按下
2. 本地麦克风录音
3. 通过 `doubaoime-asr` 调豆包逆向接口
4. 消费 `INTERIM_RESULT / FINAL_RESULT`
5. 审阅窗口 + LLM 建议 + 插入

### 退出主线的主要原因

- 服务端 `INTERIM_RESULT` 和 `FINAL_RESULT` 稳定性不可控
- 长段和中英混输时容易出现“先对后错”
- 需要大量链路补丁，维护成本高
- 与当前“手机上直接用真实豆包输入法”的方案相比，证据链更弱

### 旧主代码的关键结构

```python
def _on_press(self):
    self.typer.save_focus()
    self.tray.set_state(STATE_RECORDING)
    self.gui.show_recording()
    asyncio.run_coroutine_threadsafe(self._start_session(...), self._loop)

async def _record_and_transcribe(self, session_seq: int) -> str:
    async for response in transcribe_realtime(...):
        if response.type == ResponseType.FINAL_RESULT:
            final_parts.append(response.text)
        elif response.type == ResponseType.INTERIM_RESULT:
            self.gui.update_interim(response.text)
```

### 旧依赖

- `doubaoime-asr`
- `sounddevice`
- `numpy`
- `pynput`
- `opuslib`

这些依赖不再属于当前主线。
