import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApprovalPanel } from "../ApprovalPanel";

async function fillForm(user: ReturnType<typeof userEvent.setup>, reason: string, approver: string) {
  await user.type(screen.getByLabelText("사유"), reason);
  await user.type(screen.getByLabelText("승인자"), approver);
}

describe("ApprovalPanel — 정상 시나리오(happy path)", () => {
  it("사유·승인자를 입력하고 승인 버튼을 누르면 onSubmit이 호출된다", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ApprovalPanel onSubmit={onSubmit} />);

    await fillForm(user, "재고 확보 완료, 승인합니다", "김담당");
    await user.click(screen.getByRole("button", { name: "승인" }));

    expect(onSubmit).toHaveBeenCalledWith("approve", "재고 확보 완료, 승인합니다", "김담당");
  });
});

describe("ApprovalPanel — 입력 검증", () => {
  it("사유를 입력하지 않으면 onSubmit을 호출하지 않고 검증 메시지를 보여준다", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ApprovalPanel onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("승인자"), "김담당");
    await user.click(screen.getByRole("button", { name: "승인" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/사유를 입력/)).toBeInTheDocument();
  });

  it("조건부승인은 사유가 10자 미만이면 onSubmit을 호출하지 않는다", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ApprovalPanel onSubmit={onSubmit} />);

    await fillForm(user, "짧은사유", "김담당");
    await user.click(screen.getByRole("button", { name: "조건부승인" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/10자 이상/)).toBeInTheDocument();
  });

  it("조건부승인이 아니면 10자 미만 사유도 통과한다", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ApprovalPanel onSubmit={onSubmit} />);

    await fillForm(user, "반려함", "김담당");
    await user.click(screen.getByRole("button", { name: "반려" }));

    expect(onSubmit).toHaveBeenCalledWith("reject", "반려함", "김담당");
  });
});

describe("ApprovalPanel — 제출 상태", () => {
  it("isSubmitting이 true면 모든 버튼이 비활성화된다", () => {
    render(<ApprovalPanel isSubmitting />);
    expect(screen.getByRole("button", { name: "승인" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "반려" })).toBeDisabled();
  });

  it("submitError가 있으면 에러 메시지를 보여준다", () => {
    render(<ApprovalPanel submitError="서버 오류" />);
    expect(screen.getByText(/서버 오류/)).toBeInTheDocument();
  });
});
