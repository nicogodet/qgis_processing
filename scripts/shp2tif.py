"""
Model exported as python.
Name : shp2tif
Group : Post Traitement
With QGIS : 31203
"""

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingUtils,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterField,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterDefinition,
    QgsRasterLayer,
    QgsProject,
)
import processing


class Shp2tif(QgsProcessingAlgorithm):
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "couche",
                "Couche de points à interpoler",
                types=[QgsProcessing.TypeVectorPoint],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                "z_field",
                "Champ à interpoler",
                type=QgsProcessingParameterField.Numeric,
                parentLayerParameterName="couche",
                allowMultiple=False,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "resolutiondurasterdusortie",
                "Résolution du raster du sortie",
                type=QgsProcessingParameterNumber.Integer,
                minValue=0.01,
                defaultValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                "Raster",
                "Raster de surface libre",
                optional=False,
                fileFilter="Fichier TIF (*.tif)",
                createByDefault=True,
                defaultValue=None,
            )
        )
        param = QgsProcessingParameterNumber(
            "las_kill",
            "Paramètre -kill las2dem",
            type=QgsProcessingParameterNumber.Integer,
            minValue=1,
            defaultValue=100,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}

        layer = QgsProcessingUtils.mapLayerFromString(
            parameters["couche"], context=context
        )

        tempTXT = QgsProcessingUtils.generateTempFilename("txt_temp.txt")
        tempLAS = QgsProcessingUtils.generateTempFilename("las_temp.las")
        if parameters["Raster"] == "TEMPORARY_OUTPUT":
            parameters["Raster"] = QgsProcessingUtils.generateTempFilename("tif_temp.tif")
        
        output_file = open(tempTXT, "w")
        
        # Get the features and properly rewrite them as lines
        for feat in layer.getFeatures():
            featGeom = feat.geometry()
            if featGeom.wkbType() in [1, 1001, 2001, 3001, -2147483647]:
                output_file.write(
                    "%s\t%s\t%s\n"
                    % (
                        str(featGeom.asPoint().x()),
                        str(featGeom.asPoint().y()),
                        str(feat[parameters["z_field"]]),
                    )
                )
            elif featGeom.wkbType() in [4, 1004, 2004, 3004, -2147483644]:
                output_file.write(
                    "%s\t%s\t%s\n"
                    % (
                        str(featGeom.asMultiPoint()[0].x()),
                        str(featGeom.asMultiPoint()[0].y()),
                        str(feat[parameters["z_field"]]),
                    )
                )
            else:
                output_file.close()
                return {}
        output_file.close()

        # txt2las
        alg_params = {
            "ADDITIONAL_OPTIONS": "",
            "CPU64": True,
            "EPSG_CODE": 25832,
            "GUI": False,
            "INPUT_GENERIC": tempTXT,
            "PARSE": "xyz",
            "PROJECTION": 0,
            "SCALE_FACTOR_XY": 0.01,
            "SCALE_FACTOR_Z": 0.01,
            "SKIP": 0,
            "SP": 0,
            "UTM": 0,
            "VERBOSE": False,
            "OUTPUT_LASLAZ": tempLAS,
        }
        outputs["Txt2las"] = processing.run(
            "LAStools:txt2las",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # las2dem
        alg_params = {
            "ADDITIONAL_OPTIONS": "-kill " + str(parameters["las_kill"]),
            "ATTRIBUTE": 0,
            "CPU64": True,
            "FILTER_RETURN_CLASS_FLAGS1": 0,
            "GUI": False,
            "INPUT_LASLAZ": tempLAS,
            "PRODUCT": 0,
            "STEP": parameters["resolutiondurasterdusortie"],
            "USE_TILE_BB": False,
            "VERBOSE": False,
            "OUTPUT_RASTER": parameters["Raster"],
        }
        outputs["Las2dem"] = processing.run(
            "LAStools:blast2dem",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Charger la couche dans le projet
        pathCouche = parameters["Raster"]
        nomCouche = parameters["Raster"].split("/")[-1]
        rlayer = QgsRasterLayer(
            parameters["Raster"],
            parameters["Raster"].split("/")[-1],
            "gdal",
        )
        QgsProject.instance().addMapLayer(rlayer)
        return results
        
    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def name(self):
        return "shp2tif"

    def displayName(self):
        return "Shapefile -> tif"

    def group(self):
        return "Interpolation"

    def groupId(self):
        return "Interpolation"

    def createInstance(self):
        return Shp2tif()
