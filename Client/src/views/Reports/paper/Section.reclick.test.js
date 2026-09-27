/**
 * A jump link to a collapsible section opens it. The hash change opens it the first time; a second
 * click on the same link, after the reader closed the section again, changes no hash and fires no
 * hash change, so the section also opens on a click of any link to it (2026-09-26).
 */
import "@testing-library/jest-dom";
import { render, screen, fireEvent, act } from "@testing-library/react";
import Section from "./Section";

function Page() {
  return (
    <>
      <a href="#sec-a">Go to A</a>
      <Section id="sec-a" question="Is A open?" answer="A's answer." collapsible>
        <p>A's body</p>
      </Section>
    </>
  );
}

const body = () => document.getElementById("sec-a-body");

describe("a jump link to a closed section opens it every time", () => {
  afterEach(() => { window.history.replaceState(null, "", "/"); });

  it("opens on the first click, and again on a second click after it was closed", () => {
    render(<Page />);
    expect(body()).not.toBeVisible();
    act(() => {
      window.history.replaceState(null, "", "#sec-a");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    fireEvent.click(screen.getByText("Go to A"));
    expect(body()).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Is A open\?/ }));
    expect(body()).not.toBeVisible();
    // the hash is already #sec-a: no hash change fires
    fireEvent.click(screen.getByText("Go to A"));
    expect(body()).toBeVisible();
  });

  it("a click on a link to another section leaves this one closed", () => {
    render(<><a href="#elsewhere">Elsewhere</a><Page /></>);
    fireEvent.click(screen.getByText("Elsewhere"));
    expect(body()).not.toBeVisible();
  });
});
