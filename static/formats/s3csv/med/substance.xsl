<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

    <!-- **********************************************************************
         Active Substances (medication) - CSV Import Stylesheet

         CSV fields:
         Designation............string........med_substance.name
         Comments...............string........med_substance.comments

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

        <resource name="med_substance">
            <data field="name">
                <xsl:value-of select="col[@field='Designation']"/>
            </data>
            <data field="comments">
                <xsl:value-of select="col[@field='Comments']/text()"/>
            </data>
        </resource>

    </xsl:template>

    <!-- ****************************************************************** -->

</xsl:stylesheet>
