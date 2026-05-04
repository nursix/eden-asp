<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

    <!-- **********************************************************************
         Medical Parameters - CSV Import Stylesheet

         CSV fields:

         Organisation...........string.......Organisation Name
         Parameter Group........string.......Parameter Group Name (optional)
         Sample Type............string.......Sample Type (as Code::Designation)
         Designation............string.......Designation
         Abbreviation...........string.......Abbreviation
         Qualitative............boolean......Parameter is qualitative (Y|N)
         Unit...................string.......Unit of Measure
         Precision..............integer......Value Precision (number of decimals)
         Instructions...........string.......Instructions
         Comments...............string.......Comments

    *********************************************************************** -->
    <xsl:import href="../commons.xsl"/>

    <xsl:output method="xml"/>

    <xsl:key name="organisations" match="row" use="col[@field='Organisation']"/>
    <xsl:key name="parameter_groups" match="row" use="concat(col[@field='Parameter Group']/text(), col[@field='Organisation']/text())"/>
    <xsl:key name="sample_types" match="row" use="col[@field='Sample Type']"/>

    <!-- ****************************************************************** -->
    <xsl:template match="/">
        <s3xml>
            <!-- Organisations -->
            <xsl:for-each select="//row[generate-id(.)=generate-id(key('organisations', col[@field='Organisation'])[1])]">
                <xsl:call-template name="Organisation"/>
            </xsl:for-each>

            <!-- Parameter Groups -->
            <xsl:for-each select="//row[generate-id(.)=generate-id(key('parameter_groups', concat(col[@field='Parameter Group']/text(), col[@field='Organisation']/text()))[1])]">
                <xsl:call-template name="ParameterGroup"/>
            </xsl:for-each>

            <!-- Sample Types -->
            <xsl:for-each select="//row[generate-id(.)=generate-id(key('sample_types', col[@field='Sample Type'])[1])]">
                <xsl:call-template name="SampleType"/>
            </xsl:for-each>

            <xsl:apply-templates select="table/row"/>
        </s3xml>
    </xsl:template>

    <!-- ****************************************************************** -->
    <xsl:template match="row">

        <xsl:variable name="OrgName" select="col[@field='Organisation']/text()"/>

        <xsl:variable name="GrpName" select="col[@field='Parameter Group']/text()"/>

        <xsl:variable name="SampleType" select="col[@field='Sample Type']/text()"/>
        <xsl:variable name="SampleTypeCode" select="normalize-space(substring-before($SampleType, '::'))"/>
        <xsl:variable name="SampleTypeName" select="normalize-space(substring-after($SampleType, '::'))"/>

        <xsl:variable name="Name" select="normalize-space(col[@field='Designation'])"/>
        <xsl:variable name="Abbrv" select="normalize-space(col[@field='Abbreviation'])"/>

        <xsl:if test="$Name!='' and $Abbrv!=''">
            <resource name="med_parameter">
                <data field="name">
                    <xsl:value-of select="$Name"/>
                </data>
                <data field="abbrv">
                    <xsl:value-of select="$Abbrv"/>
                </data>

                <!-- Link to Organisation -->
                <xsl:if test="$OrgName!=''">
                    <reference field="organisation_id" resource="org_organisation">
                        <xsl:attribute name="tuid">
                            <xsl:value-of select="concat('ORG:', $OrgName)"/>
                        </xsl:attribute>
                    </reference>
                </xsl:if>

                <!-- Link to Parameter Group -->
                <xsl:if test="$GrpName!=''">
                    <reference field="parameter_group_id" resource="med_parameter_group">
                        <xsl:attribute name="tuid">
                            <xsl:value-of select="concat('PG:', $OrgName, ':', $GrpName)"/>
                        </xsl:attribute>
                    </reference>
                </xsl:if>

                <!-- Link to Sample Type -->
                <xsl:if test="$SampleTypeCode!='' and $SampleTypeName!=''">
                    <reference field="sample_type_id" resource="med_sample_type">
                        <xsl:attribute name="tuid">
                            <xsl:value-of select="concat('ST:', $SampleType)"/>
                        </xsl:attribute>
                    </reference>
                </xsl:if>

                <xsl:call-template name="Boolean">
                    <xsl:with-param name="column">Qualitative</xsl:with-param>
                    <xsl:with-param name="field">qualitative</xsl:with-param>
                    <xsl:with-param name="default">false</xsl:with-param>
                </xsl:call-template>
                <data field="um">
                    <xsl:value-of select="col[@field='Unit']/text()"/>
                </data>
                <data field="precsn">
                    <xsl:value-of select="col[@field='Precisions']/text()"/>
                </data>
                <data field="instructions">
                    <xsl:value-of select="col[@field='Instructions']/text()"/>
                </data>
                <data field="comments">
                    <xsl:value-of select="col[@field='Comments']/text()"/>
                </data>

            </resource>
        </xsl:if>

    </xsl:template>

    <!-- ****************************************************************** -->
    <xsl:template name="Organisation">

        <xsl:variable name="OrgName" select="col[@field='Organisation']/text()"/>

        <resource name="org_organisation">
            <xsl:attribute name="tuid">
                <xsl:value-of select="concat('ORG:', $OrgName)"/>
            </xsl:attribute>
            <data field="name"><xsl:value-of select="$OrgName"/></data>
        </resource>

    </xsl:template>

    <!-- ****************************************************************** -->
    <xsl:template name="ParameterGroup">

        <xsl:variable name="GrpName" select="col[@field='Parameter Group']/text()"/>
        <xsl:variable name="OrgName" select="col[@field='Organisation']/text()"/>

        <xsl:if test="$GrpName!=''">
            <resource name="med_parameter_group">
                <xsl:attribute name="tuid">
                    <xsl:value-of select="concat('PG:', $OrgName, ':', $GrpName)"/>
                </xsl:attribute>
                <data field="name"><xsl:value-of select="$GrpName"/></data>
                <xsl:if test="$OrgName!=''">
                    <reference field="organisation_id" resource="org_organisation">
                        <xsl:attribute name="tuid">
                            <xsl:value-of select="concat('ORG:', $OrgName)"/>
                        </xsl:attribute>
                    </reference>
                </xsl:if>
            </resource>
        </xsl:if>

    </xsl:template>

    <!-- ****************************************************************** -->
    <xsl:template name="SampleType">

        <xsl:variable name="SampleType" select="col[@field='Sample Type']/text()"/>
        <xsl:variable name="SampleTypeCode" select="normalize-space(substring-before($SampleType, '::'))"/>
        <xsl:variable name="SampleTypeName" select="normalize-space(substring-after($SampleType, '::'))"/>

        <xsl:if test="$SampleTypeCode!='' and $SampleTypeName!=''">
            <resource name="med_sample_type">
                <xsl:attribute name="tuid">
                    <xsl:value-of select="concat('ST:', $SampleType)"/>
                </xsl:attribute>
                <data field="name"><xsl:value-of select="$SampleTypeName"/></data>
                <data field="code"><xsl:value-of select="$SampleTypeCode"/></data>
            </resource>
        </xsl:if>

    </xsl:template>

    <!-- END ************************************************************** -->

</xsl:stylesheet>
