<?xml version="1.0"?>
<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

    <!-- **********************************************************************
         Needs Assessment Site Type - CSV Import Stylesheet

         CSV column...........Format..........Content

         Type.................string..........Type Name
         Comments.............string..........Comments

    *********************************************************************** -->
    <xsl:output method="xml"/>

    <!-- ****************************************************************** -->
    <xsl:template match="/">
        <s3xml>
            <xsl:apply-templates select="./table/row"/>
        </s3xml>
    </xsl:template>

    <!-- ****************************************************************** -->
    <xsl:template match="row">
        <xsl:variable name="Type" select="col[@field='Type']/text()"/>
        <xsl:if test="$Type!=''">
            <resource name="req_need_site_type">
                <data field="name"><xsl:value-of select="$Type"/></data>
                <data field="comments"><xsl:value-of select="col[@field='Comments']"/></data>
            </resource>
        </xsl:if>
    </xsl:template>

    <!-- ****************************************************************** -->

</xsl:stylesheet>
