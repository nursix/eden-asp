# Smoke Tests: Visits every URL inside Eden and reports it on the console if they
# are broken
# This suite is designed to be run inside EdenTest without generating reports
# or logs(as generating them would require a lot of time)

# Usage with timestamped output file: python web2py.py --no-banner -M -S eden  -R applications/eden/tests/edentest_runner.py -A  smoke_tests  -o NONE -l NONE
# Usage with given name of output file: python web2py.py --no-banner -M -S eden  -R applications/eden/tests/edentest_runner.py -A  smoke_tests  -o NONE -l NONE -v filename:smoke_tests.txt

*** Settings ***
Resource  ../../resources/main.robot
Library  edentest_smoke.py  ${BASE URL}  ${DO NOT FOLLOW}  ${EXT LINKS}
Library  DateTime
Library  OperatingSystem

*** Variables ***
# It contains the configuration settings to run the smoke tests

# Setting the depth till where URLs will be parsed
${MAXDEPTH}=  ${SMOKETEST DEPTH} +1
# Follow external links
${EXT LINKS}  ${False}
${PAGE LOAD TIMEOUT}  0.25
${ELEMENT LOAD TIMEOUT}  0.50
# Starting URL
${START URL}  ${PROTO}://${SERVER}/${APPNAME}/${SMOKETEST START}
# Every URL Must contain the root. If you want to test at a module level and
# ignore other modules, just set the Root URL to that module
${ROOT URL}  ${SMOKETEST ROOT}
# All the URLs containing these will be ignored eg: default/index
@{DO NOT FOLLOW}  _language=  logout  appadmin  delete  .pdf  clean  #totop-

*** Keywords ***

Get All URLs From Current Page
    [Documentation]  Gets all the URLs from the current page
    ...  by executing the javascript in the file get_links.js
    ${output}=  Execute Javascript  ${CURDIR}/get_links.js
    RETURN  ${output}

Set Selenium Timeouts
    Set Selenium Timeout  ${PAGE LOAD TIMEOUT}
    Set Selenium Implicit Wait  ${ELEMENT LOAD TIMEOUT}

Check For Invalidity
    [Documentation]  Check for invalid controller or function
    [Arguments]  ${Failed URL}  ${level}
    ${passed}=  Run Keyword and Return Status  Page Should Contain  invalid ${level}
    Run Keyword If  not ${passed}  Return From Keyword  ${0}
    ${message}=  Get Text  xpath=/html/body/h1
    Log  FAILED: ${Failed URL} - ${message}  WARN
    Append To File  ${Log File}  FAILED: ${Failed URL} - ${message}\n
    RETURN  ${1}

Check For Errors
    [Documentation]  Look for invalidity or tickets. If found returns 1
    ...  otherwise returns 0
    [Arguments]  ${Failed URL}
    ${passed}=  Check For Invalidity  ${Failed URL}  controller
    Return From Keyword If  ${passed}==${1}  ${1}

    ${passed}=  Check For Invalidity  ${Failed URL}  function
    Return From Keyword If  ${passed}==${1}  ${1}

    ${passed}=  Check For Ticket And Catch Exception  ${Failed URL}
    Run Keyword If  ${passed}!=0  Append To File  ${Log File}  ${passed}[0]${passed}[1]
    Login To Eden If Not Logged In  ${VALID USER}  ${VALID PASSWORD}
    Return From Keyword If  ${passed}!=${0}  ${1}

    RETURN  ${0}

Visit URLs And Return ToVisit
    [Documentation]  Visits the URLs present in URL List and
    ...  returns the set of URLs to be visited in the next iteration
    ...  that is the next depth of urls.
    [Arguments]  ${URL List}

    ${To Visit}=  Create List
    ${URLs Failed}=  Set Variable  ${0}

    # Just a check
    Remove Duplicates  ${URL List}

    FOR  ${Url}  IN  @{URL List}
      Go To  ${Url}
      Append To file  ${Log File}  ${URL}\n
      ${status}=  Check For Errors  ${Url}
      ${URLs Failed}=  Increment URLs Failed  ${URLs Failed}  ${status}
      Run Keyword If  ${status}==0  Append To File  ${Log File}  Status: PASSED\n\n
      Run Keyword If  ${status}!=0  Append To File  ${Log File}  Status: FAILED\n\n
      Continue For Loop If  ${status}!=0
      Append To List  ${ALREADY VISITED}  ${Url}
      ${Current Urls}=  Get All URLs From Current Page
      ${To Visit}=  Add Current Urls to ToVisit Urls  ${Current Urls}  ${To Visit}  ${URL List}
    END
    RETURN  ${To Visit}  ${URLs Failed}

Add Current Urls to ToVisit Urls
    [Documentation]  This appends the URLs parsed from the current
    ...  page into the ToVisit URLs
    [Arguments]  ${Current Urls}  ${To Visit}  ${URL List}
    FOR  ${Url}  IN  @{Current Urls}
      ${output}=  Check If Url Should be Skipped  ${Url}
      Continue For Loop If  ${output} == 1
      ${Url}=  Strip Url of Unwanted Parts  ${Url}
      ${output}=  Check If Not Already Added or Visited  ${ALREADY VISITED}  ${To Visit}  ${URL List}  ${Url}
      Run Keyword If  ${output} == 0  Append To List  ${To Visit}  ${Url}
    END

    Remove Duplicates  ${To Visit}
    RETURN  ${To Visit}

Create Log File
    ${name}=  Get Variable Value  ${filename}  default
    ${Time}=  Get Current Date  result_format=datetime
    ${Time}=  Convert Date  ${Time}  result_format=%d.%m.%Y.%H.%M

    Run Keyword If  '${name}'=='default'  Set Global Variable  ${Log File}  ${Time}_smoke_tests_log.txt
    Run Keyword If  '${name}'!='default'  Set Global Variable  ${Log File}  ${name}

    Remove File  ${Log File}
    Create File  ${Log File}

*** Test Cases ***
Every page is showing correctly
    Set Selenium Timeouts
    Register Keyword To Run On Failure  Nothing
    Create Log File

    Login To Eden  ${VALID USER}  ${VALID PASSWORD}
    ${To Visit}=  Create List  ${START URL}

    ${ALREADY VISITED}=  Create List
    Set Suite Variable  ${ALREADY VISITED}

    ${URLs Failed}=  Set Variable  ${0}
    ${URLs Count}=  Set Variable  ${0}

    FOR  ${Depth}  IN RANGE  ${MAXDEPTH}
      ${Start Time}=  Get Current Date  result_format=timestamp
      # Just a check
      Remove Duplicates  ${To Visit}
      # Get the count of URLs to be visited
      ${len}=  Get Length  ${To Visit}
      ${URLs Count}=  Evaluate  ${URLs Count}+${len}
      # Visit every URL, get other URLs in the page, report errors
      ${To Visit}  ${lf}=  Visit URLs And Return ToVisit  ${To Visit}
      # Increment URLs failed count
      ${URLs Failed}=  Evaluate  ${URLs Failed} + ${lf}
      # Get the time taken to run for this level
      ${End Time}=  Get Current Date  result_format=timestamp
      ${Run Time}=  Subtract Date From Date  ${End Time}  ${Start Time}
      ${Run Time}=  Convert Time  ${Run Time}  verbose  exclude_milles=yes
      # Log results of this level
      Log  \n Depth ${Depth} \n Number of URLs Visited - ${len} \n Time Taken - ${Run Time} \n  console=yes
    END
    # Log Results of the suite
    Log  \n Total URLs Visited - ${URLs Count} \n Total URLs Failed - ${URLs Failed}  console=yes

    Append to file  ${Log File}  \n Total URLs Visited - ${URLs Count} \n Total URLs Failed - ${URLs Failed}
    Run Keyword if  ${URLs Failed}!=0  Fail  Broken URLs Found
