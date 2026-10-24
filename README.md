# Apple TV 联动小米／峰米激光投影仪

2026-10-24 在 FengMiProjA2（Android 9，固件 9.12.5.118）和 iStoreOS 软路由上实测。`bridge.py` 是实际部署并经多轮开关机验证的脚本备份，没有改变运行逻辑。Home Assistant 不需要持续运行。

## 原理

- Apple TV 通过 HDMI-CEC 发送待机指令，但这台投影仪固件没有因此熄灭光源。
- 软路由保持 ADB 连接，每两秒执行 `dumpsys hdmi_control`，读取投影仪的 CEC 消息历史。
- 发现新的、来自 CEC 逻辑地址 4、目标为 0 或广播地址 15 的 `Standby` 消息，且投影仪处于 `Awake`，发送 `input keyevent KEYCODE_SLEEP`。
- 开机由投影仪原生 CEC 自动唤醒负责，脚本不负责检测 Apple TV 开机。音量仍通过现有遥控器方式控制。
- 初次启动忽略已有消息；连续运行时对最新待机记录去重。连接异常等待五秒后重试。

固定连接：Apple TV 在 HDMI 1，CEC 逻辑地址为 4；投影仪 IP 为 `192.168.0.111`，ADB 端口为 `5555`。不依赖 Apple TV 的 IP。请在 DHCP 服务器固定投影仪 IP；地址改变时修改脚本。

**不要增加当前 CEC 路由必须为 HDMI 1 的条件。** Apple TV 休眠时，投影仪可能在脚本查询前已把路由从 `0x1000` 清成 `0x0000`，这种检查会导致第二次关机失效。该脚本按固定连接用途处理来自地址 4 的待机指令，不检查当前页面。

## 恢复部署

仓库不包含密码、ADB 私钥、Home Assistant 配置或配对凭据。以下 Dockerfile/Compose 是便于重新部署的配套文件，尚未在当前路由器上构建验证；实际运行版本复用了路由器已有的 Home Assistant 镜像及其 Python 依赖。已验证依赖版本为 `adb-shell 0.4.4`、`rsa 4.9`。

1. 准备支持 ARM64 或本机架构的 Docker、Docker Compose；路由器必须能够访问投影仪。打开投影仪开发者选项及 ADB。
2. 创建 `keys/`，放入该投影仪已授权的 `adbkey` 和 `adbkey.pub`，私钥权限设为 `600`。若密钥丢失，可生成新密钥：

   ```sh
   mkdir -p keys
   docker build -t apple-tv-projector-cec:local .
   docker run --rm -v "$PWD/keys:/keys" apple-tv-projector-cec:local \
     python -c "from adb_shell.auth.keygen import keygen; keygen('/keys/adbkey')"
   chmod 600 keys/adbkey
   ```

3. 启动服务，在投影仪弹出的 USB 调试窗口中勾选“始终允许”并允许。可能需要先唤醒投影仪：

   ```sh
   docker compose up -d --build
   docker logs -f apple-tv-projector-cec
   ```

4. 在投影仪设置开启 CEC 和自动唤醒。本机已验证可通过授权的 ADB 设置：

   ```sh
   adb connect 192.168.0.111:5555
   adb -s 192.168.0.111:5555 shell settings put global hdmi_control_auto_wakeup_enabled 1
   adb -s 192.168.0.111:5555 shell dumpsys hdmi_control
   ```

   确认输出 `mAutoWakeup: true`。其他型号不能保证使用相同设置。

5. 用 Apple TV 遥控器连续测试至少两轮开关机，关闭后等约五秒。系统状态可用 `dumpsys power` 验证：休眠时 `mWakefulness=Asleep`、`Display Power: state=OFF`，还应目视确认光源熄灭。

## 当前实测部署与维护

软路由上的源文件目录为 `/mnt/mmcblk0p4/Configs/apple-tv-projector/`，容器名为 `apple-tv-projector-cec`，重启策略为 `unless-stopped`。现有容器把 `bridge.py` 挂载为 `/bridge.py`，密钥目录只读挂载到 `/keys`。密钥原位置为 `/mnt/mmcblk0p4/Configs/HA2/android/`；请单独妥善保管，不要提交 Git。

```sh
docker logs --tail 50 apple-tv-projector-cec
docker restart apple-tv-projector-cec
docker stop apple-tv-projector-cec
docker update --restart=no apple-tv-projector-cec
```

停止服务不影响原装遥控器。若要撤销本次开启的原生自动唤醒：

```sh
adb -s 192.168.0.111:5555 shell settings delete global hdmi_control_auto_wakeup_enabled
```

Home Assistant 内之前创建的两条 Apple TV 电源联动自动化已停用：旧版 Apple TV 库不能可靠读取该设备的电源状态。当前联动与 Home Assistant 的 Apple TV 集成无关。

注意：脚本依赖此固件的 `dumpsys hdmi_control` 文本格式及 CEC 地址；更换设备、固件或 HDMI 拓扑后应重新验证。服务初次启动不补执行启动前的关机消息。

## 局域网精简订阅服务

另见 [iptv/README.md](iptv/README.md)：为 APTV 提供精简频道列表，成功每30分钟更新，失败每5分钟重试。独立容器运行，不影响 CEC 联动；不包含真实订阅地址和频道缓存。
