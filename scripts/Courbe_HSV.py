"""
Model exported as python.
Name : Calcul de la courbe HSV d'une retenue de barrage
Group : A_définir
With QGIS : 31604
"""

from qgis.core import (
    QgsVectorLayer,
    QgsFeatureRequest,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsWkbTypes,
    QgsProject,
    QgsProcessing,
    QgsProcessingUtils,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFeatureSink,
)
from qgis.PyQt.QtCore import QVariant

import processing
import os


class CalculHSV(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    EMPRISE = "EMPRISE"
    DZ = "DZ"
    MAXZ = "MAXZ"
    OUTPUT = "OUTPUT"
    OUTPUT2 = "OUTPUT2"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT,
                "Modèle Numérique de Terrain",
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.EMPRISE,
                "Emprise vectorielle de la retenue",
                types=[QgsProcessing.TypeVectorPolygon],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DZ,
                "Pas d'espace altimétrique",
                type=QgsProcessingParameterNumber.Double,
                minValue=0.01,
                defaultValue=0.5,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAXZ,
                "Arrêter la courbe HSV au dessus de l'altimétrie",
                type=QgsProcessingParameterNumber.Double,
                minValue=0,
                optional=True,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT,
                "Courbe HSV (pour Excel)",
                fileFilter="Fichiers Texte (*.html)",
                createByDefault=True,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT2,
                "Courbe HSV (couche sans géométrie pour Qgis)",
                optional=True,
                type=QgsProcessing.TypeVector,
                createByDefault=False,
                defaultValue=None,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(5, model_feedback)
        results = {}
        outputs = {}

        MNT = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        emprise = self.parameterAsVectorLayer(parameters, self.EMPRISE, context)
        dZ = self.parameterAsDouble(parameters, self.DZ, context)
        fichier_html = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        fichier_txt = "{}.txt".format(os.path.splitext(fichier_html)[0])

        if parameters[self.MAXZ] == None:
            maxZ = 99999
        else:
            maxZ = self.parameterAsDouble(parameters, self.MAXZ, context)

        # Découper un raster selon une couche de masquage
        alg_params = {
            "ALPHA_BAND": False,
            "CROP_TO_CUTLINE": True,
            "DATA_TYPE": 0,
            "EXTRA": "",
            "INPUT": MNT.source(),
            "KEEP_RESOLUTION": True,
            "MASK": emprise,
            "MULTITHREADING": False,
            "NODATA": None,
            "OPTIONS": "",
            "SET_RESOLUTION": False,
            "SOURCE_CRS": None,
            "TARGET_CRS": "ProjectCrs",
            "X_RESOLUTION": None,
            "Y_RESOLUTION": None,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["Clip"] = processing.run(
            "gdal:cliprasterbymasklayer",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Polygones Courbes de niveau
        alg_params = {
            "BAND": 1,
            "CREATE_3D": False,
            "EXTRA": "",
            "FIELD_NAME_MAX": "ELEV_MAX",
            "FIELD_NAME_MIN": "ELEV_MIN",
            "IGNORE_NODATA": False,
            "INPUT": outputs["Clip"]["OUTPUT"],
            "INTERVAL": dZ,
            "NODATA": None,
            "OFFSET": 0,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["PolygonesCourbesDeNiveau"] = processing.run(
            "gdal:contour_polygon",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Collecter les géométries
        alg_params = {
            "FIELD": ["ELEV_MIN"],
            "INPUT": outputs["PolygonesCourbesDeNiveau"]["OUTPUT"],
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["CollectGeom"] = processing.run(
            "native:collect", alg_params, context=context, feedback=feedback, is_child_algorithm=True
        )

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Calcul "Surface"
        layer = QgsProcessingUtils.generateTempFilename("layer.shp")
        alg_params = {
            "FIELD_LENGTH": 12,
            "FIELD_NAME": "Surface",
            "FIELD_PRECISION": 2,
            "FIELD_TYPE": 0,
            "FORMULA": "$area",
            "INPUT": outputs["CollectGeom"]["OUTPUT"],
            "OUTPUT": layer,
        }
        outputs["CalculSurface"] = processing.run(
            "native:fieldcalculator",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        fields = QgsFields()
        fields.append(QgsField("Z", QVariant.Double))
        fields.append(QgsField("Surface", QVariant.Double))
        fields.append(QgsField("Volume", QVariant.Double))
        (couche, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT2,
            context,
            fields,
            QgsWkbTypes.NoGeometry,
            QgsProject.instance().crs(),
        )

        with open(fichier_html, "w") as f_html, open(fichier_txt, "w") as f_txt:
            f_html.write(
                """
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Courbe HSV</title>
    <style>
    html {
      font-family: sans-serif;
    }

    table {
      border-collapse: collapse;
      border: 2px solid rgb(200,200,200);
      letter-spacing: 1px;
      font-size: 0.8rem;
    }
    
    td, th {
      border: 1px solid rgb(190,190,190);
      padding: 10px 20px;
    }

    td {
      text-align: center;
    }

    caption {
      padding: 10px;
    }
    </style>
  </head>
  <body>
    <h1>Courbe HSV</h1>

    <table>
        <tr>
            <th>Z</th>
            <th>Surface (m&sup2;)</th>
            <th>Volume (m&sup3;)</th>
        </tr>
"""
            )
            f_txt.write("Z\tSurface\tVolume\n")

            z = []
            surface = []
            volume = []

            vLayer = QgsVectorLayer(layer, "temp")

            request = QgsFeatureRequest()

            # Ordonner par ELEV_MIN ascendant
            clause = QgsFeatureRequest.OrderByClause("ELEV_MIN", ascending=True)
            orderby = QgsFeatureRequest.OrderBy([clause])
            request.setOrderBy(orderby)

            for current, feat in enumerate(vLayer.getFeatures(request)):
                if feedback.isCanceled():
                    return {}
                if feat["ELEV_MAX"] > maxZ:
                    break
                if current == 0:
                    z.append(round(feat["ELEV_MAX"], 2))
                    surface.append(round(feat["Surface"], 2))
                    volume.append(round(feat["Surface"] * dZ / 2, 2))
                else:
                    z.append(round(feat["ELEV_MAX"], 2))
                    surface.append(round(surface[-1] + feat["Surface"], 2))
                    volume.append(round(feat["Surface"] * dZ / 2 + surface[-2] * dZ + volume[-1], 2))

                self.writeHTMLTableLine(f_html, z[-1], surface[-1], volume[-1])
                f_txt.write("{}\t{}\t{}\n".format(z[-1], surface[-1], volume[-1]))

                if couche is not None:
                    fet = QgsFeature()
                    tabAttr = [z[-1], surface[-1], volume[-1]]
                    fet.setAttributes(tabAttr)
                    couche.addFeature(fet)

            f_html.write(
                """
    </table>

  </body>
</html>
"""
            )

        return {self.OUTPUT: fichier_html, self.OUTPUT2: dest_id}

    def writeHTMLTableLine(self, f, *arg):
        f.write("<tr>\n")
        for a in arg:
            f.write("<td>{}</td>\n".format(str(a)))
        f.write("</tr>\n")

    def name(self):
        return "Calcul de la courbe HSV d'une retenue de barrage"

    def displayName(self):
        return "Calcul de la courbe HSV d'une retenue de barrage"

    def group(self):
        return "HSV"

    def groupId(self):
        return "HSV"

    def createInstance(self):
        return CalculHSV()
