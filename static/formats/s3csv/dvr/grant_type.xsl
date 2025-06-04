<?xml version="1.0"?>
<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

    <!-- **********************************************************************
         DVR Grant Type - CSV Import Stylesheet

         CSV column..................Format..........Content

         Name........................string..........Type Name
         Description.................text............Type Description
         Entity......................string..........Granting Entity
         Aid Type....................string..........Type of Aid
                                                     "CASH"|"SUPPLY"|"WORK"|"COUNSEL"|"SHELTER"|"OTHER"
         Unit........................string..........Unit of Measure (e.g. currency, or "hours")
         Comments....................string..........Comments

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

        <resource name="dvr_grant_type">

            <data field="name">
                <xsl:value-of select="normalize-space(col[@field='Name']/text())"/>
            </data>
            <data field="description">
                <xsl:value-of select="col[@field='Description']/text()"/>
            </data>
            <data field="granting_entity">
                <xsl:value-of select="normalize-space(col[@field='Entity']/text())"/>
            </data>
            <data field="aid_type">
                <xsl:attribute name="value">
                    <xsl:value-of select="normalize-space(col[@field='Aid Type']/text())"/>
                </xsl:attribute>
            </data>
            <data field="um">
                <xsl:value-of select="normalize-space(col[@field='Unit']/text())"/>
            </data>
            <data field="comments">
                <xsl:value-of select="col[@field='Comments']/text()"/>
            </data>

        </resource>

    </xsl:template>

    <!-- ****************************************************************** -->

</xsl:stylesheet>
