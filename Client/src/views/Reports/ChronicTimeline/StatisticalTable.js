/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { currentTargetText } from "utils/participantTargets";
import { useMemo } from "react";
import * as Math from "mathjs";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { Table, TableHead, TableRow, TableCell, TableBody } from "@mui/material";
import { annotationValues } from "graphing-utility/annotationValues";

export default function StatisticalTable({data, availableChannels, annotations}) {
  const rows = useMemo(() => annotations.filter(annotation => annotation.Duration > 0).flatMap(annotation =>
    availableChannels.active.flatMap(channel => {
      const values = annotationValues(data, annotation, channel);
      if (!values.length) return [];
      const result = `${Math.mean(values).toFixed(2)} ± ${Math.std(values).toFixed(2)}`;
      return [{annotation, channel, result}];
    })
  ), [data, annotations, availableChannels.active]);

  return (
      <MDBox px={2} pb={2} style={{overflowX: "auto", maxHeight: "100vh"}}>
        <Table size="large" style={{marginTop: 20, display: "block", height: "fit-content"}}>
          <TableHead sx={{display: "table-header-group", position: "sticky", top: 0, zIndex: 1}}>
            <TableRow sx={{background: "white"}}>
              <TableCell variant="head" style={{width: "15%", minWidth: 150, verticalAlign: "bottom", paddingBottom: 0, paddingTop: 0}}>
                <MDTypography variant="span" fontSize={12} fontWeight={"bold"} style={{cursor: "pointer"}} onClick={()=>{}}>
                  {"Event"}
                </MDTypography>
              </TableCell>
              <TableCell variant="head" style={{width: "15%", minWidth: 150, verticalAlign: "bottom", paddingBottom: 0, paddingTop: 0}}>
                <MDTypography variant="span" fontSize={12} fontWeight={"bold"} style={{cursor: "pointer"}} onClick={()=>{}}>
                  {"Channel"}
                </MDTypography>
              </TableCell>
              <TableCell variant="head" style={{width: "15%", minWidth: 150, verticalAlign: "bottom", paddingBottom: 0, paddingTop: 0}}>
                <MDTypography variant="span" fontSize={12} fontWeight="bold">Data Range</MDTypography>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map(({annotation, channel, result}) => (
              <TableRow key={annotation.Id + "_" + channel}>
                <TableCell><MDTypography variant="span" fontSize={12} fontWeight="bold">{annotation.Name}</MDTypography></TableCell>
                <TableCell><MDTypography variant="span" fontSize={12} fontWeight="bold">{currentTargetText(channel)}</MDTypography></TableCell>
                <TableCell><MDTypography variant="span" fontSize={12} fontWeight="bold">{result}</MDTypography></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </MDBox>
  );
}
