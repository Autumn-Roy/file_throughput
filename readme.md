# 文件传输能力测评工具

## 概述

本工具用于测试不同超算集群之间的数据传输能力。它能够自动化生成不同大小的文件、开启传输任务并监控、校验文件完整性，生成传输速率、成功率、文件完整性校验结果。

## 功能特点

- 自动化文件生成：多种不同大小的文件，模拟真实情况

- 精准测量：准确记录文件传输时间并计算平均速率

- 全面监控：实时跟踪数据传输速率，在屏幕输出进度条

- 专业分析报告：数据传输速率、文件校验完整性等指标

- 场景化覆盖：支持灵活配置，根据不同测试集群调整配置文件即可


## 系统要求

• Python 3.6+

• 必需Python包：

  - `fpdf2`
  - `matplotlib`
  - `numpy`
  - `pandas`
  - `python-dateutil`
  - `tabulate`


• LINUX依赖库：openssh-client、coreutils


## 安装步骤

克隆仓库或下载源代码

## 使用方法

1. 准备配置文件(文本格式)，示例如下：

```txt
[DEFAULT]
target_ip = efixxx.hpccube.com
port = 6xx
username = scnet_xxx
password = 5b9-4082-adef-xxxx198322d
key_path = ./xxx.txt
remote_dir = /file_transport
ssh_ip = eshexxx.hpccube.com
ssh_port = 6xxx
```

2. 运行基准测试：

```bash
python file_throughput.py -c config.ini
```

配置参数说明

| 参数名 | 类型 | 描述 | 默认值 |
|--------|------|------|--------|
| target_ip | string | 文件传输目标地址 | 无(必填) |
| port | integer | 文件传输目标端口 | 无(必填) |
| username | string | 作业传输时使用的账户名称 | 无(必填) |
| password | string | 对应账户名称的登录密码 | 无(必填) |
| key_path | string | 每个节点的最大核心数string | 无(必填) |
| remote_dir | string | 远端存储目录路径 | /file_transport |
| ssh_ip | string | 文件校验时使用的目标IP地址 | 与target_ip一致 |
| ssh_port | integer | 文件校验时使用的目标端口 | 与port一致 |

## 输出结果

测试完成后将生成：
1. 文件生成信息：包含每个文件的大小、名称、创建成功与否
2. 数据传输过程：包含文件传输顺序、进度条
3. 传输用时
4. 文件完整性校验：包含每个文件的校验进度、成功与否

## 注意事项

1. 确保运行工具的用户有权限登录目标传输地址，并且能够访问指定端口
2. 预留至少110GB的存储空间用于生成及传输数据
3. 运行前检查目标地址和端口，确认能够联通且具有访问权限
4. 建议至少在3个不同时间段执行测试程序以获得准确结果

技术支持

如有任何问题，请联系开发者或提交issue。
