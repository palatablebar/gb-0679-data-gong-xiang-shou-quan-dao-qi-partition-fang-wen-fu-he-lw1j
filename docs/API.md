# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

POST /api/grants/<id>/renewal 为授权定版季度续期结论，body含grant_end、decision（续期/停用）、extended_end（续期必填且须晚于原截止）；按(授权,季度)幂等，重试返回原结论，冲突返回409。GET /api/renewals 列出已定版结论。解析后的结论（含到期未确认的系统停用结论）并入批次参数，供访问裁决、冲突检查与证据导出共用。
