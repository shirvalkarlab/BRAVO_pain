/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { SessionController } from "database/session-control";
import { identityMatrix, computeElectrodePlacement, parseBinarySTL } from ".";
import * as THREE from "three";
import * as math from "mathjs";

/**
 * Wrapper for retriving models from UF BRAVO Platform Backend Server. 
 *
 * @param {string} directory - Directory that store the model. Typically the Patient ID.
 * @param {Object} item - The model object that describe the available models in the server. 
 * @param {string} color - Hex-encoded color string to force model into specific colors. 
 * 
 * @return {Object[]} Array of controllable items that contain both data and description of the model downloaded. 
 */
const retrieveModels = async (participant_uid, item, color) => {
  const controlledItems = [];
  
  if (item.DataType == "STL") {
    const response = await SessionController.query("/api/downloadData", {
      "ParticipantId": participant_uid,
      "CacheType": "queryImageModel",
      "DataId": item.Id,
      "FileType": item.DataType
    }, {}, null, "arraybuffer");
    const data = parseBinarySTL(response.data);
    controlledItems.push({
      id: item.Id,
      filename: item.Name,
      type: item.DataType,
      downloaded: true,
      data: data,
      opacity: 1,
      color: color ? color : data.color,
      matrix: identityMatrix(),
      show: true,
    });
  
  } else if (item.type == "volume") {
    const response = await SessionController.query("/api/queryImageModel", {
      "Directory": participant_uid,
      "FileName": item.file,
      "FileMode": item.mode,
      "FileType": item.type
    }, {}, null, "arraybuffer");
    return response.data;

  } else if (item.type == "tracts") {
    const response = await SessionController.query("/api/queryImageModel", {
      "Directory": participant_uid,
      "FileName": item.file,
      "FileMode": item.mode,
      "FileType": item.type
    });
    controlledItems.push({
      filename: item.file,
      type: item.type,
      downloaded: true,
      data: response.data.points,
      thickness: 1,
      color: color ? color : "#FFFFFF",
      matrix: identityMatrix(),
      show: true,
    });

  } else if (item.type == "points") {
    const response = await SessionController.query("/api/queryImageModel", {
      "Directory": participant_uid,
      "FileName": item.file,
      "FileMode": item.mode,
      "FileType": item.type
    });
    controlledItems.push({
      filename: item.file,
      type: item.type,
      downloaded: true,
      data: response.data.points,
      thickness: 1,
      color: color ? color : "#FFFFFF",
      matrix: identityMatrix(),
      show: true,
    });

  } else if (item.type == "sphere") {
    controlledItems.push({
      filename: item.file,
      type: item.type,
      downloaded: true,
      data: item.targetPoints,
      color: color ? color : "#FFFFFF",
      matrix: identityMatrix(),
      show: true,
    });

  } else if (item.type == "electrode") {
    const response = await SessionController.query("/api/queryImageModel", {
      "Directory": participant_uid,
      "ElectrodeName": item.electrode,
      "FileName": item.file,
      "FileMode": item.mode,
      "FileType": item.type
    }, {}, null, "arraybuffer");
    const data = parseBinarySTL(response.data);
    controlledItems.push({
      filename: item.file,
      data: data,
      color: color ? color : data.color,
    });

  }
  return controlledItems;

};

export default retrieveModels; 