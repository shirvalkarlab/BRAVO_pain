/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useCallback, useMemo } from 'react';
import { Handle, Position } from '@xyflow/react';

import { Card } from '@mui/material';
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from 'database/session-control';

const handleStyle = { left: 10 };
 
function RecordingNode({ id, data }) {
  const onChange = useCallback((evt) => {
    
  }, []);

  return useMemo(() => (
    <div style={data.Result ? {background: "#c6ff00", padding: 15} : {padding: 15}}>
      <MDBox>
        <MDTypography variant={"h5"} fontWeight={"bold"}>
          {data.Name.length > 0 ? data.Name : data.Id}
        </MDTypography>
        <MDTypography variant={"subtitle1"} fontSize={12}>
          {data.Type}
        </MDTypography>
        <MDTypography variant={"p"} fontSize={15}>
          {new Date(data.Date*1000).toLocaleString("en-US", {...SessionController.getTimezoneName(data.Timezone)})}
        </MDTypography>
      </MDBox>
      <Handle type="source" position={Position.Bottom} id={id+"_RecordingOutput"} />
    </div>
  ), [data]);
}

export default RecordingNode;