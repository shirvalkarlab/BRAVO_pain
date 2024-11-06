/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import axios from "axios";

import { ERRORCODE } from "./api-codes";
import { dictionary } from "assets/translation.js";
import MuiAlertDialog from "components/MuiAlertDialog"

//import { Manager } from "socket.io-client"

const timezoneNameDict={
  "UTC-12:00": "Etc/GMT+12",
  "UTC-11:00": "Etc/GMT+11",
  "UTC-10:00": "Etc/GMT+10",
  "UTC-09:30": "Pacific/Marquesas",
  "UTC-09:00": "Etc/GMT+9",
  "UTC-08:00": "Etc/GMT+8",
  "UTC-07:00": "Etc/GMT+7",
  "UTC-06:00": "Etc/GMT+6",
  "UTC-05:00": "Etc/GMT+5",
  "UTC-04:00": "Etc/GMT+4",
  "UTC-03:30": "America/St_Johns",
  "UTC-03:00": "Etc/GMT+3",
  "UTC-02:00": "Etc/GMT+2",
  "UTC-01:00": "Etc/GMT+1",
  "UTC+00:00": "Etc/GMT",
  "UTC+01:00": "Etc/GMT-1",
  "UTC+02:00": "Etc/GMT-2",
  "UTC+03:00": "Etc/GMT-3",
  "UTC+03:30": "Iran",
  "UTC+04:00": "Etc/GMT-4",
  "UTC+04:30": "Asia/Kabul",
  "UTC+05:00": "Etc/GMT-5",
  "UTC+05:30": "Asia/Colombo",
  "UTC+05:45": "Asia/Kathmandu",
  "UTC+06:00": "Etc/GMT-6",
  "UTC+06:30": "Asia/Yangon",
  "UTC+07:00": "Etc/GMT-7",
  "UTC+08:00": "Etc/GMT-8",
  "UTC+09:00": "Etc/GMT-9",
  "UTC+09:30": "Australia/Darwin",
  "UTC+10:00": "Etc/GMT-10",
  "UTC+10:30": "Australia/LHI",
  "UTC+11:00": "Etc/GMT-11",
  "UTC+12:00": "Etc/GMT-12",
  "UTC+13:00": "Etc/GMT-13",
  "UTC+14:00": "Etc/GMT-14"
};

const timezoneOffsetDict={
  "UTC-12:00": -12*3600000,
  "UTC-11:00": -11*3600000,
  "UTC-10:00": -10*3600000,
  "UTC-09:30": -9*3600000-30*60000,
  "UTC-09:00": -9*3600000,
  "UTC-08:00": -8*3600000,
  "UTC-07:00": -7*3600000,
  "UTC-06:00": -6*3600000,
  "UTC-05:00": -5*3600000,
  "UTC-04:00": -4*3600000,
  "UTC-03:30": -3*3600000-30*60000,
  "UTC-03:00": -3*3600000,
  "UTC-02:00": -2*3600000,
  "UTC-01:00": -1*3600000,
  "UTC+00:00": 0,
  "UTC+01:00": 1*3600000,
  "UTC+02:00": 2*3600000,
  "UTC+03:00": 3*3600000,
  "UTC+03:30": 3*3600000+30*60000,
  "UTC+04:00": 4*3600000,
  "UTC+04:30": 4*3600000+30*60000,
  "UTC+05:00": 5*3600000,
  "UTC+05:30": 5*3600000+30*60000,
  "UTC+05:45": 5*3600000+45*60000,
  "UTC+06:00": 6*3600000,
  "UTC+06:30": 6*3600000+30*60000,
  "UTC+07:00": 7*3600000,
  "UTC+08:00": 8*3600000,
  "UTC+09:00": 9*3600000,
  "UTC+09:30": 9*3600000+30*60000,
  "UTC+10:00": 10*3600000,
  "UTC+10:30": 10*3600000+30*60000,
  "UTC+11:00": 11*3600000,
  "UTC+12:00": 12*3600000,
  "UTC+13:00": 13*3600000,
  "UTC+14:00": 14*3600000
};

export const SessionController = (function () {
  //let server = "https://bravo-server.jcagle.solutions";
  let server = "http://localhost:3001";
  let connectionStatus = false;

  let synced = false;
  let session = {language: "en"};
  let user = {};
  let authToken = "";
  let refreshToken = "";
  let serverVersion = 0;
  let newestVersion = 0;

  const setAuthToken = (token) => {
    authToken = token;
  };

  const getAuthToken = () => {
    return authToken;
  };

  const setRefreshToken = (token) => {
    refreshToken = token;
    localStorage.setItem("refreshToken", refreshToken);
  };

  const getRefreshToken = () => {
    return refreshToken;
  };

  const setServer = (address) => {
    server = address;
    localStorage.setItem("serverAddress", server);
  };

  const getServer = () => {
    return server;
  };

  const getConnectionStatus = () => {
    return {
      version: serverVersion,
      update: newestVersion,
      status: connectionStatus
    };
  };

  const query = (url, form, config, timeout, responseType) => {
    return axios.post(server + url, form, {
      timeout: timeout,
      responseType: responseType,
      headers: {
        "Authorization": authToken === "" ? null : "Bearer " + authToken,
        ...config,
      }
    });
  };

  const displayError = (error, setAlert) => {
    if (setAlert && error.response) {
      var errorMessage = dictionary.ErrorMessage.UNKNOWN_ERROR[session.language];
      if (error.response.status === 500) {
        errorMessage = dictionary.ErrorMessage.INTERNAL_SERVER_ERROR[session.language];
      } else if (error.response.status === 404) {
        errorMessage = dictionary.ErrorMessage.ENDPOINT_NOT_EXIST[session.language];
      } else if (error.response.status === 403) {
        errorMessage = dictionary.ErrorMessage.PERMISSION_DENIED[session.language];
      } else if (error.response.status === 400) {
        for (var key of Object.keys(ERRORCODE)) {
          if (ERRORCODE[key] == error.response.data.code) {
            errorMessage = dictionary.ErrorMessage[key][session.language];
            break;
          }
        }
        if (errorMessage == dictionary.ErrorMessage.UNKNOWN_ERROR[session.language]) {
          console.log(ERRORCODE);
          console.log(error.response.data);
        }
      } else if (error.response.status == 401) {
        setAuthToken("");
        setRefreshToken("");
        errorMessage = dictionary.ErrorMessage["CONNECTION_TIMEDOUT"][session.language]
      } else {
        console.log(error);
      }
      setAlert(
        <MuiAlertDialog title={"ERROR"} message={errorMessage}
          handleClose={() => setAlert()} 
          handleConfirm={() => setAlert()}/>
      );
    } else {
      console.log(error);
    }
  };

  const verifyServerAddress = async (storedServer) => {
    // Reset Credentials in case of 401
    authToken = "";
    server = storedServer;

    connectionStatus = false;
    try {
      const response = await query("/api/handshake", {}, {}, 2000);
      if (response.status == 200) {
        serverVersion = response.data.CurrentVersion;
        newestVersion = response.data.DockerVersionLatest;
        connectionStatus = true;
      }
    } catch (error) {
      serverVersion = "";
      console.log(error);
    }

    if (connectionStatus) setServer(server);
    return connectionStatus;
  };

  const refreshAuthToken = async () => {
    if (refreshToken === "") return {status: 500};

    try {
      const refreshResponse = await query("/api/authRefresh", {
        refresh: refreshToken
      });
      setAuthToken(refreshResponse.data.access);
      return refreshResponse;
    } catch(error) {
      setAuthToken("");
      setRefreshToken("");
      return error;
    }
  };

  const verifyToken = async (token) => {
    // Token can be empty, which is common if you are not logged in.
    if (token === "") return;

    refreshToken = token;
    const response = await refreshAuthToken();
    if (response.status !== 200) {
      setRefreshToken("");
    }
  };

  const syncSession = async () => {
    if (localStorage.getItem("sessionContext")) {
      session = JSON.parse(localStorage.getItem("sessionContext"));
    }
    const response = await query("/api/querySessions", {
      session: session,
    });
    session = {...session, ...response.data.session};

    if (!Object.keys(session).includes("IndefiniteStreamLayout")) {
      session.BrainSenseSurveyLayout = {};
      session.BrainSensestreamLayout = {};
      session.IndefiniteStreamLayout = {};
      session.ChronicBrainSenseLayout = {};
    }

    localStorage.setItem("sessionContext", JSON.stringify(session));
    user = response.data.user;
    return getSession();
  };

  const isSynced = () => {
    return synced;
  };

  const getSession = () => {
    return {
      ...session,
      user: user,
    }
  };

  const setSession = (type, value) => {
    query("/api/updateSession", {[type]: value}).catch((error) => console.log(error));
    session[type] = value;
    session["lastActive"] = new Date().getTime();
    localStorage.setItem("sessionContext", JSON.stringify(session));
  };

  const getDateTimeOptions = (type) => {
    if (type == "DateFull") {
      return {dateStyle: "full"};
    } else if (type == "DateLong") {
      return {dateStyle: "long"};
    } else if (type == "DateNumeric") {
      return {year: 'numeric', month: 'numeric', day: 'numeric'};
    } else {
      return {weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'}
    }
  };

  const getTimezoneName = (UTCTime) => {
    return timezoneNameDict[UTCTime] ? {timeZone: timezoneNameDict[UTCTime]} : {};
  }

  const getTimezoneOffset = (startTime, UTCTime) => {
    const localOffset = new Date(startTime).getTimezoneOffset() * -60000
    return timezoneOffsetDict[UTCTime] === undefined ? 0 : (localOffset - timezoneOffsetDict[UTCTime]);
  }

  const handShake = async () => {
    if (Object.keys(user).length === 0 || refreshToken === "") {
      return false;
    }
    
    try {
      await query("/api/handshake");
      return true;
    } catch (error) {
      nullifyUser();
      return false;
    }
  };

  const authenticate = (username, password, rememberMe) => {
    return query("/api/authenticate", {Email: username, Password: password, Persistent: rememberMe ? true : false});
  };

  const register = (username, email, password, institute) => {
    return query("/api/registration", {UserName: username, Email: email, Institute: institute, Password: password});
  };

  const logout = () => {
    return query("/api/logout", {
      refresh: refreshToken,
    });
  };

  const nullifyUser = () => {
    user = {};
    session = {};
    authToken = "";
    if (localStorage.getItem("accessToken")) {
      localStorage.setItem("accessToken", authToken);
    }
    if (localStorage.getItem("refreshToken")) {
      localStorage.setItem("refreshToken", refreshToken);
    }
    if (localStorage.getItem("sessionContext")) {
      localStorage.setItem("sessionContext", session);
    }
  };

  const setUser = (account) => {
    user = account;
  };

  const getUser = () => {
    return user;
  };

  const setPatientID = async (id) => {
    try {
      await query("/api/setPatientID", { id: id });  
      session.patientID = id;
      return true;
    } catch (error) {
      return false;
    }
  };

  const getPatientInfo = (patientID) => {
    return query("/api/queryPatientInfo", {
      id: patientID
    });
  };

  const setPageIndex = (type, index) => {
    setSession(type+"PageIndex", index);
  };

  return {
    setAuthToken: setAuthToken,
    getAuthToken: getAuthToken,
    setRefreshToken: setRefreshToken,
    getRefreshToken: getRefreshToken,
    refreshAuthToken: refreshAuthToken,
    setServer: setServer,
    getServer: getServer,
    getConnectionStatus: getConnectionStatus,

    verifyServerAddress: verifyServerAddress,
    verifyToken: verifyToken,

    query: query,
    displayError: displayError,
    syncSession: syncSession,
    getSession: getSession,
    setSession: setSession,

    getDateTimeOptions: getDateTimeOptions,
    getTimezoneName: getTimezoneName,
    getTimezoneOffset: getTimezoneOffset,

    isSynced: isSynced,
    handShake: handShake,

    authenticate: authenticate,
    register: register,
    nullifyUser: nullifyUser,
    logout: logout,
    getUser: getUser,
    setUser: setUser,

    setPatientID: setPatientID,
    getPatientInfo: getPatientInfo,
    setPageIndex: setPageIndex
  }

})();