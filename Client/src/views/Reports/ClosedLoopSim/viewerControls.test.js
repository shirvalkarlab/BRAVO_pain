import React from "react";
import {render, screen, fireEvent} from "@testing-library/react";
import {ThemeProvider} from "@mui/material/styles";
import theme from "assets/theme";
import {PlatformContextProvider} from "context";
import {SessionController} from "database/session-control";
import DeveloperMenu from "./DeveloperMenu";
import RecomputeBar from "../RecomputeBar";
jest.mock("database/session-control",()=>({SessionController:{isReadOnly:jest.fn()}}));
const wrap=ui=><ThemeProvider theme={theme}><PlatformContextProvider initialStates={{language:"en"}}>{ui}</PlatformContextProvider></ThemeProvider>;
test("viewer developer controls cannot load or clear a band, while stored result metadata remains",()=>{
 SessionController.isReadOnly.mockReturnValue(true);
 const load=jest.fn(),clear=jest.fn();
 render(wrap(<DeveloperMenu onLoad={load} onClear={clear}><span>Stored result metadata</span></DeveloperMenu>));
 fireEvent.click(screen.getByRole("button",{name:/More actions/}));
 const button=screen.getByRole("button",{name:"Load a saved band file"});
 expect(button.disabled).toBe(true);fireEvent.click(button);expect(load).not.toHaveBeenCalled();
 expect(screen.queryByRole("button",{name:"Clear the chosen band"})).toBeNull();
 expect(screen.getByText("Stored result metadata")).toBeTruthy();
});
test("viewer sees provenance without an active recompute button",()=>{
 SessionController.isReadOnly.mockReturnValue(true);const run=jest.fn();
 render(wrap(<RecomputeBar title="Synthetic analysis" computedAt={Date.now()} onRecompute={run}/>));
 const button=screen.getByRole("button",{name:"Recompute anyway"});
 expect(button.disabled).toBe(true);fireEvent.click(button);expect(run).not.toHaveBeenCalled();
 expect(screen.getByText(/Switching views/)).toBeTruthy();
});
test("owner retains recompute controls",()=>{
 SessionController.isReadOnly.mockReturnValue(false);const run=jest.fn();
 render(wrap(<RecomputeBar onRecompute={run}/>));
 fireEvent.click(screen.getByRole("button",{name:"Recompute anyway"}));expect(run).toHaveBeenCalledTimes(1);
});
