/**
 * 用户可见术语与设备分组初始状态的回归约束。
 *
 * 组件测试环境目前不含 DOM renderer，因此设备分组用源码不变量守住：初始状态必须
 * 明确回落到 false，不能再根据房间数或索引自动展开。统计文案直接检查 i18n 资源，
 * 同时确保普通用户标题与开发者精确口径并存。
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { formatRelativeDuration } from "@/components/PerfKpiCards";

const componentPath = fileURLToPath(
  new URL("../src/components/DevicesByRoom.tsx", import.meta.url),
);
const zhPerfPath = fileURLToPath(
  new URL("../src/i18n/locales/zh/perf.json", import.meta.url),
);

describe("设备房间分组", () => {
  const source = readFileSync(componentPath, "utf8");

  it("所有房间初始收起，仍允许用户逐个展开", () => {
    expect(source).toContain("expanded[room] ?? false");
    expect(source).not.toContain("defaultOpen");
    expect(source).toContain("setExpanded");
  });
});

describe("性能总览文案", () => {
  const perf = JSON.parse(readFileSync(zhPerfPath, "utf8")).perf as Record<
    string,
    string
  >;

  it("首层 KPI 使用普通用户能理解的名称", () => {
    expect(perf.kpiCycle).toBe("已处理任务");
    expect(perf.kpiShouldProcess).toBe("收到任务");
    expect(perf.kpiGateFilterRate).toBe("无需深度分析");
    expect(perf.kpiDropRate).toBe("未进入实时处理");
    expect(perf.kpiOmniErrorRate).toBe("AI 分析失败率");
    expect(perf.kpiRtfP95).toBe("整体处理相对耗时");
    expect(perf.kpiOmniRtfP95).toBe("AI 分析相对耗时");
    expect(perf.kpiAgentCall).toBe("触发后续任务");
  });

  it("说明保留可核对的技术指标名称和窗口调度口径", () => {
    expect(perf.kpiGateFilterRateHint).toContain("Gate 过滤率");
    expect(perf.kpiDropRateHint).toContain("窗口丢弃率");
    expect(perf.kpiDropRateHint).toContain("较旧片段");
    expect(perf.kpiDropRateHint).toContain("积压片段");
    expect(perf.kpiOmniErrorRateHint).toContain("Omni 错误率");
    expect(perf.kpiRtfP95Hint).toContain("P95");
    expect(perf.kpiRtfP95Hint).toContain("低于 1");
    expect(perf.kpiOmniRtfP95Hint).toContain("P95");
    expect(perf.kpiAgentCallHint).toContain("Agent 调用");
  });

  it("相对耗时显示倍数，零样本不伪装成零耗时", () => {
    expect(formatRelativeDuration(0)).toBe("—");
    expect(formatRelativeDuration(0.03)).toBe("0.03×");
    expect(formatRelativeDuration(1)).toBe("1.00×");
  });
});
