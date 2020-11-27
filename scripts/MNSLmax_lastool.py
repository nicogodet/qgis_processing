"""
Model exported as python.
Name : MNSLmax_lastools
Group : Post Traitement
With QGIS : 31203
"""

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingUtils
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterVectorDestination
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProcessingParameterFile
from qgis.core import QgsProcessingParameterFileDestination
from qgis.core import QgsProcessingParameterField
from qgis.core import QgsProcessingParameterDefinition
import processing


class Mnslmax_lastools(QgsProcessingAlgorithm):
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "pointsresultats", "Points résultats", types=[QgsProcessing.TypeVectorPoint], defaultValue=None,
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
                "Raster de surface libre (La sortie temporaire ne fonctionne pas)",
                optional=False,
                fileFilter="Fichier TIF (*.tif)",
                createByDefault=True,
                defaultValue=None,
            )
        )
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

        tempFolder = QgsProcessingUtils.tempFolder() + "/"

        # Extraire par attribut
        alg_params = {
            "FIELD": "HAUTEUR D'",
            "INPUT": parameters["pointsresultats"],
            "OPERATOR": 3,
            "VALUE": parameters["hmin"],
            "OUTPUT": tempFolder + "points_extraits.shp",
        }
        outputs["ExtraireParAttribut"] = processing.run(
            "native:extractbyattribute", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )
        # results['Points_extraits'] = outputs['ExtraireParAttribut']['OUTPUT']

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # v.distance
        alg_params = {
            "GRASS_MIN_AREA_PARAMETER": 0.0001,
            "GRASS_OUTPUT_TYPE_PARAMETER": 1,
            "GRASS_REGION_PARAMETER": None,
            "GRASS_SNAP_TOLERANCE_PARAMETER": -1,
            "GRASS_VECTOR_DSCO": "",
            "GRASS_VECTOR_EXPORT_NOCAT": False,
            "GRASS_VECTOR_LCO": "",
            "column": [self.renameGrass(parameters["sl_field"])],
            "dmax": -1,
            "dmin": -1,
            "from": parameters["pointsresultats"],
            "from_type": [0, 1, 3],
            "to": outputs["ExtraireParAttribut"]["OUTPUT"],
            "to_column": self.renameGrass(parameters["sl_field"]),
            "to_type": [0, 1, 3],
            "upload": [6],
            "from_output": tempFolder + "voisin.shp",
            "output": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["Vdistance"] = processing.run(
            "grass7:v.distance", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )
        # results['Plus_proche_voisin'] = outputs['Vdistance']['from_output']

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Assigner une projection
        alg_params = {
            "CRS": "ProjectCrs",
            "INPUT": outputs["Vdistance"]["from_output"],
            "OUTPUT": tempFolder + "reproj.shp",
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
            "OUTPUT": tempFolder + "xy.shp",
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
                {"expression": "x", "length": 14, "name": "X", "precision": 4, "type": 6,},
                {"expression": "y", "length": 14, "name": "Y", "precision": 4, "type": 6,},
                {
                    "expression": self.renameGrass(parameters["sl_field"]),
                    "length": 14,
                    "name": "Z_w",
                    "precision": 4,
                    "type": 6,
                },
            ],
            "INPUT": outputs["AjouterLesChampsXyLaCouche"]["OUTPUT"],
            "OUTPUT": tempFolder + "refac.shp",
        }
        outputs["RefactoriserLesChamps"] = processing.run(
            "qgis:refactorfields", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )

        layer = QgsProcessingUtils.mapLayerFromString(outputs["RefactoriserLesChamps"]["OUTPUT"], context=context)

        # Set the path for the output file
        output_file = open(tempFolder + "txt_temp.txt", "w")

        # Get the features and properly rewrite them as lines
        for feat in layer.getFeatures():
            output_file.write("%s\t%s\t%s\n" % (str(feat["X"]), str(feat["Y"]), str(feat["Z_w"])))
            # unicode_message = msgout.encode('utf-8')
            # output_file.write(unicode_message)
        output_file.close()

        # txt2las
        alg_params = {
            "ADDITIONAL_OPTIONS": "",
            "CPU64": True,
            "EPSG_CODE": 25832,
            "GUI": False,
            "INPUT_GENERIC": tempFolder + "txt_temp.txt",
            "PARSE": "xyz",
            "PROJECTION": 0,
            "SCALE_FACTOR_XY": 0.01,
            "SCALE_FACTOR_Z": 0.01,
            "SKIP": 0,
            "SP": 0,
            "UTM": 0,
            "VERBOSE": False,
            "OUTPUT_LASLAZ": tempFolder + "las_temp.las",
        }
        outputs["Txt2las"] = processing.run(
            "LAStools:txt2las", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
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
            "INPUT_LASLAZ": tempFolder + "las_temp.las",
            "PRODUCT": 0,
            "STEP": parameters["resolutiondurasterdusortie"],
            "USE_TILE_BB": False,
            "VERBOSE": False,
            "OUTPUT_RASTER": parameters["Raster"],
        }
        outputs["Las2dem"] = processing.run(
            "LAStools:las2dem", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Charger la couche dans le projet
        nomCouche = parameters["Raster"]
        nomCouche = nomCouche.split("/")[-1]
        alg_params = {"INPUT": parameters["Raster"], "NAME": nomCouche}
        outputs["ChargerLaCoucheDansLeProjet"] = processing.run(
            "native:loadlayer", alg_params, context=context, feedback=feedback, is_child_algorithm=True,
        )
        return results

    def name(self):
        return "MNSLmax_lastools"

    def displayName(self):
        return "(Pré 3.14) Modèle Numérique de Surface Libre TELEMAC"

    def group(self):
        return "Post Traitement"

    def groupId(self):
        return "Post Traitement"

    def shortHelpString(self):
        return "Algorithme de génération du raster de surface libre d'un résultat de modèle TELEMAC2D à partir des points du maillage extrait avec PostTelemac."

    def createInstance(self):
        return Mnslmax_lastools()

    def renameGrass(self, a):
        a = a.replace("'", "_")
        a = a.replace(" ", "_")
        return a
