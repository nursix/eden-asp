<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

    <!-- **********************************************************************
         Membership Types - CSV Import Stylesheet

         CSV fields:
         Designation............string........med_vaccination_type.name
         Vaccine Type...........string........med_vaccination_type.vaccine_type
         Comments...............string........med_vaccination_type.comments

    *********************************************************************** -->
    <xsl:output method="xml"/>

    <!-- ****************************************************************** -->

    <xsl:template match="/">
        <s3xml>
            <xsl:apply-templates select="table/row"/>
        </s3xml>
    </xsl:template>

    <!-- ****************************************************************** -->
    <xsl:template match="row">

        <xsl:variable name="Type" select="col[@field='Vaccine Type']/text()"/>

        <resource name="med_vaccination_type">
            <data field="name">
                <xsl:value-of select="col[@field='Designation']"/>
            </data>
            <xsl:if test="$Type!=''">
                <data field="vaccine_type"><xsl:value-of select="$Type"/></data>
            </xsl:if>
            <data field="comments">
                <xsl:value-of select="col[@field='Comments']/text()"/>
            </data>
        </resource>

    </xsl:template>

    <!-- ****************************************************************** -->

</xsl:stylesheet>
