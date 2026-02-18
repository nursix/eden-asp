<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

    <!-- **********************************************************************
         Sample Types - CSV Import Stylesheet

         CSV fields:
         Designation............string........med_sample_type.name
         Code...................string........med_sample_type.code
         Instructions...........string........med_sample_type.instructions
         Comments...............string........med_sample_type.comments

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

        <xsl:variable name="Name" select="normalize-space(col[@field='Designation'])"/>
        <xsl:variable name="Code" select="normalize-space(col[@field='Code'])"/>

        <xsl:if test="$Name!='' and $Code!=''">
            <resource name="med_sample_type">
                <data field="name">
                    <xsl:value-of select="$Name"/>
                </data>
                <data field="code">
                    <xsl:value-of select="$Code"/>
                </data>
                <data field="instructions">
                    <xsl:value-of select="col[@field='Instructions']"/>
                </data>
                <data field="comments">
                    <xsl:value-of select="col[@field='Comments']/text()"/>
                </data>
            </resource>
        </xsl:if>

    </xsl:template>

    <!-- ****************************************************************** -->

</xsl:stylesheet>
