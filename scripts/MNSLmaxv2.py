"""
Model exported as python.
Name : MNSLmax_lastools
Group : Post Traitement
With QGIS : 312
"""

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingUtils,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterField,
    QgsProcessingParameterDefinition,
    QgsRasterLayer,
    QgsProject,
)
import processing


class MnslmaxV2(QgsProcessingAlgorithm):
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "pointsresultats",
                "Points résultats",
                types=[QgsProcessing.TypeVectorPoint],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "hmin",
                "Seuil d'hauteur d'eau minimale pour l'extraction des points",
                type=QgsProcessingParameterNumber.Double,
                minValue=0.001,
                defaultValue=0.1,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "resolutiondurasterdusortie",
                "Résolution du raster du sortie",
                type=QgsProcessingParameterNumber.Integer,
                minValue=0.1,
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
        param = QgsProcessingParameterField(
            "h_field",
            "Champ d'hauteur d'eau",
            type=QgsProcessingParameterField.Numeric,
            parentLayerParameterName="pointsresultats",
            allowMultiple=False,
            defaultValue="HAUTEUR D'",
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        
        param = QgsProcessingParameterField(
            "sl_field",
            "Champ de Surface Libre",
            type=QgsProcessingParameterField.Numeric,
            parentLayerParameterName="pointsresultats",
            allowMultiple=False,
            defaultValue="SURFACE LI",
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

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
        feedback = QgsProcessingMultiStepFeedback(7, model_feedback)
        results = {}
        outputs = {}

        # Extraire par attribut
        alg_params = {
            "FIELD": parameters["h_field"],
            "INPUT": parameters["pointsresultats"],
            "OPERATOR": 3,
            "VALUE": parameters["hmin"],
            "OUTPUT": QgsProcessingUtils.generateTempFilename("points_extraits.shp"),
        }
        outputs["ExtraireParAttribut"] = processing.run(
            "native:extractbyattribute", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        alg_params = {
            "DISCARD_NONMATCHING": False,
            "FIELDS_TO_COPY": [str(parameters["sl_field"])],
            "INPUT": parameters["pointsresultats"],
            "INPUT_2": outputs["ExtraireParAttribut"]["OUTPUT"],
            "MAX_DISTANCE": None,
            "NEIGHBORS": 1,
            "PREFIX": "_______Z_w",
            "OUTPUT": QgsProcessingUtils.generateTempFilename("voisin.shp"),
        }
        outputs["JoindreLesAttributsParLePlusProche"] = processing.run(
            "native:joinbynearest", alg_params, context=context, feedback=feedback, is_child_algorithm=True
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Assigner une projection
        alg_params = {
            "CRS": "ProjectCrs",
            "INPUT": outputs["JoindreLesAttributsParLePlusProche"]["OUTPUT"],
            "OUTPUT": QgsProcessingUtils.generateTempFilename("reproj.shp"),
        }
        outputs["AssignerUneProjection"] = processing.run(
            "native:assignprojection", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Ajouter les champs X/Y à la couche
        alg_params = {
            "CRS": "ProjectCrs",
            "INPUT": outputs["AssignerUneProjection"]["OUTPUT"],
            "PREFIX": "",
            "OUTPUT": QgsProcessingUtils.generateTempFilename("xy.shp"),
        }
        outputs["AjouterLesChampsXyLaCouche"] = processing.run(
            "native:addxyfields", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Refactoriser les champs
        alg_params = {
            "FIELDS_MAPPING": [
                {"expression": '"x"', "length": 14, "name": "X", "precision": 4, "type": 6,},
                {"expression": '"y"', "length": 14, "name": "Y", "precision": 4, "type": 6,},
                {"expression": '"_______Z_w"', "length": 14, "name": "Z_w", "precision": 4, "type": 6,},
            ],
            "INPUT": outputs["AjouterLesChampsXyLaCouche"]["OUTPUT"],
            "OUTPUT": QgsProcessingUtils.generateTempFilename("refac.shp"),
        }
        outputs["RefactoriserLesChamps"] = processing.run(
            "qgis:refactorfields", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )

        layer = QgsProcessingUtils.mapLayerFromString(outputs["RefactoriserLesChamps"]["OUTPUT"], context=context)

        # Set the path for the output file
        tempTXT = QgsProcessingUtils.generateTempFilename("txt_temp.txt")
        tempLAS = QgsProcessingUtils.generateTempFilename("las_temp.las")
        output_file = open(tempTXT, "w")

        # Get the features and properly rewrite them as lines
        for feat in layer.getFeatures():
            output_file.write("%s\t%s\t%s\n"
                % (
                    str(feat["X"]),
                    str(feat["Y"]),
                    str(feat["Z_w"])
                )
            )

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
            "LAStools:txt2las", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        if parameters["Raster"] == "TEMPORARY_OUTPUT":
            parameters["Raster"] = QgsProcessingUtils.generateTempFilename("tif_temp.tif")
        
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
        outputs["Blast2dem"] = processing.run(
            "LAStools:blast2dem", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
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
        
        return {}
    
    # Autres fonctions

    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading
    
    def name(self):
        return "MNSLmaxV2"

    def displayName(self):
        return "Modèle Numérique de Surface Libre TELEMAC"

    def group(self):
        return "Post Traitement"

    def groupId(self):
        return "Post Traitement"

    def shortHelpString(self):
        return "Algorithme de génération du raster de surface libre d'un résultat de modèle TELEMAC2D à partir des points du maillage extrait avec PostTelemac."

    def createInstance(self):
        return MnslmaxV2()
