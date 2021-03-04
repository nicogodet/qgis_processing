# -*- coding: utf-8 -*-

"""
***************************************************************************
    exzeco.py
    ---------------------
    Date                 : Mars 2021
    Copyright            : (C) 2021 par ISL
    Email                : athimon@isl.fr; godet@isl.fr
***************************************************************************
"""

__author__ = "Olivier ATHIMON, Nicolas GODET"
__date__ = "Mars 2021"
__copyright__ = "(C) 2021, ISL, Olivier ATHIMON, Nicolas GODET"

from qgis.core import (
    QgsProcessing,
    QgsProcessingUtils,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterRasterDestination,
    QgsRasterLayer,
    QgsProject,
)
from qgis.PyQt.QtGui import QIcon

import processing
import os

## TODO :
# [x] Modifier la fin de la boucle pour utiliser le paramètre de sortie self.OUTPUT
# [ ] Ne pas définir de raster au début de l'itération, utiliser les OUTPUT temporaires directement -> garder pour suppression aisée des fichiers intermédiaires au besoin ?
# [ ] Clarifier la doc du script
# [ ] Clean


class Exzeco(QgsProcessingAlgorithm):
    """
    Ce script est l'adaptation de la méthode ExZEco développée par le Cerema pour définir le ruissellement sur l'arc méditerranéen.

    Lien : https://www.cerema.fr/system/files/documents/2020/07/methode_exzeco_25mai2020.pdf
    """

    # Définition des constantes de paramètres
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    ITERATION = "ITERATION"
    BRUITAGE_MIN = "BRUITAGE_MIN"
    BRUITAGE_MAX = "BRUITAGE_MAX"
    SEUIL = "SEUIL"
    MINIMUMSIZEOFEXTERIORWATERSHEDBASIN = "MINIMUMSIZEOFEXTERIORWATERSHEDBASIN"
    SUPPRFICHIERSINTERMED = "SUPPRFICHIERSINTERMED"

    def name(self):
        return "exzeco"

    def displayName(self):
        return "Méthode ExZEco"

    def group(self):
        return "Ruissellement"

    def groupId(self):
        return "Ruissellement"

    def shortDescription(self):
        return "Méthode ExZEco du Cerema adaptée par ISL"

    def shortHelpString(self):
        return """
            <h2>Description de l'algorithme</h2>
            <p><img src="C:/Users/godet/Desktop/Screenshot_2.png" alt="" align="left" width="80" height="80" style="margin: 2px;"/>Exzeco est une m&eacute;thode simple, qui permet, &agrave; partir de la topographie, d&rsquo;obtenir des emprises potentiellement inondables sur de petits bassins versants.</p>
            <p><a href="http://intranet/intranet/index.php">Lien vers la notice d&eacute;taill&eacute;e d'utilisation ISL</a></p>
            <p><a href="https://www.cerema.fr/system/files/documents/2020/07/methode_exzeco_25mai2020.pdf">Lien vers le PDF descriptif du CEREMA</a></p>
            <h2>Param&egrave;tres en entr&eacute;e</h2>
            <h3>Mod&egrave;le num&eacute;rique de terrain</h3>
            <p>Mod&egrave;le Num&eacute;rique de Terrain du bassin versant</p>
            <h3>Nombre d'iteration</h3>
            <p>Nombre de passe de bruitage al&eacute;atoire du MNT.</p>
            <h3>Bruitage minimal</h3>
            <p>Il s'agit de la hauteur minimale de modification du MNT par bruitage.</p>
            <h3>Bruitage maximal</h3>
            <p>Il s'agit de la hauteur maximale de modification du MNT par bruitage.</p>
            <h3>Diviseur</h3>
            <p>A suppr si pas utile</p>
            <h3>Seuil</h3>
            <p>Seuil minimal du nombre de cellules drain&eacute;es &agrave; consid&eacute;rer pour repr&eacute;senter le ruissellement.</p>
            <p>Plus le seuil est &eacute;lev&eacute;, plus il faudra de cellules drain&eacute;es pour que cela apparaisse sur le r&eacute;sultat final.</p>
            <h3>Minimum size of exterior watershed basin</h3>
            <p>Ce param&egrave;tre permet de g&eacute;n&eacute;rer un chevelu hydrographique plus ou moins d&eacute;velopp&eacute;.</p>
            <p><a href="https://grass.osgeo.org/grass79/manuals/r.watershed.html">Lien documentation GRASS</a></p>
            <h2>Sorties</h2>
            <h3>Couche ExZEco g&eacute;n&eacute;r&eacute;e</h3>
            <p>Couche raster finale issue des it&eacute;rations successives.</p>
            <p></p>
            <p align="right">Auteur de l'algorithme : Olivier ATHIMON, Nicolas GODET</p>
            <p align="right">Auteur de l'aide : Nicolas GODET</p>
            <p align="right">Version de l'algorithme : 2.0</p>
        """

    def helpUrl(self):
        return "https://www.cerema.fr/system/files/documents/2020/07/methode_exzeco_25mai2020.pdf"

    def icon(self):
        return QIcon("C:/Users/godet/Desktop/Screenshot_2.png")

    def createInstance(self):
        return Exzeco()

    # Début du script
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT,
                "Modèle numérique de terrain",
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ITERATION,
                "Nombre d'itération",
                type=QgsProcessingParameterNumber.Integer,
                minValue=1,
                defaultValue=25,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.BRUITAGE_MIN,
                "Bruitage minimal",
                type=QgsProcessingParameterNumber.Double,
                minValue=0.01,
                defaultValue=0.01,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.BRUITAGE_MAX,
                "Bruitage maximal",
                type=QgsProcessingParameterNumber.Double,
                minValue=0.01,
                defaultValue=5,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SEUIL,
                "Seuil",
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=500,
            )
        )
        param = QgsProcessingParameterNumber(
            self.MINIMUMSIZEOFEXTERIORWATERSHEDBASIN,
            # TODO : traduire ça
            "Minimum size of exterior watershed basin",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=500,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterBoolean(
            self.SUPPRFICHIERSINTERMED,
            "Suppression des fichiers intermédaires au fur et à mesure des itérations",
            defaultValue=True,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.OUTPUT,
                "Couche ExZEco générée",
                createByDefault=True,
                defaultValue=None,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        ## Import des paramètres en tant que variables
        mnt = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        iteration = self.parameterAsInt(parameters, self.ITERATION, context)
        bruitage_min = self.parameterAsDouble(parameters, self.BRUITAGE_MIN, context)
        bruitage_max = self.parameterAsDouble(parameters, self.BRUITAGE_MAX, context)
        seuil = self.parameterAsInt(parameters, self.SEUIL, context)
        tailleMinWatershed = self.parameterAsInt(parameters, self.MINIMUMSIZEOFEXTERIORWATERSHEDBASIN, context)
        supprFichiersIntermed = self.parameterAsBoolean(parameters, self.SUPPRFICHIERSINTERMED, context)
        mntExzeco = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        ## Calcul des variables utiles au script
        # Pour le nom des fichiers créés
        len_iter = len(str(iteration))

        # Emprise du raster au format GRASS
        minX, minY, maxX, maxY = mnt.extent().toString(2).replace(" : ", ",").split(",")
        emprise = "{minX},{maxX},{minY},{maxY} [{scr_authid}]".format(
            minX=minX, maxX=maxX, minY=minY, maxY=maxY, scr_authid=mnt.crs().authid()
        )

        # Résolution du MNT d'entrée pour la taille de la cellule GRASS
        taillePixel = mnt.rasterUnitsPerPixelX()

        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(5 * iteration, model_feedback)
        results = {}
        outputs = {}

        feedback.pushInfo("Emprise calculée : {}".format(emprise))
        feedback.pushInfo("Taille pixel : {}".format(taillePixel))

        for i in range(iteration):
            # Stop l'algorithme si Cancel est cliqué
            if feedback.isCanceled():
                return {}

            # Création des fichiers temporaires interméaires
            aleatoire = QgsProcessingUtils.generateTempFilename(str(i).zfill(len_iter) + "_aleatoire.tif")
            MNTBruite = QgsProcessingUtils.generateTempFilename(str(i).zfill(len_iter) + "_MNTBruite.tif")
            surfacesDrainees = QgsProcessingUtils.generateTempFilename(str(i).zfill(len_iter) + "_surfacesDrainees.tif")
            surfacesDraineesSeuil = QgsProcessingUtils.generateTempFilename(
                str(i).zfill(len_iter) + "_surfacesDraineesSeuil.tif"
            )
            surfacesDraineesSeuilMax = QgsProcessingUtils.generateTempFilename(
                str(i).zfill(len_iter) + "_surfacesDraineesSeuilMax.tif"
            )

            feedback.setProgressText("Itération {}/{} : Création du raster aléatoire".format(i + 1, iteration))
            feedback.setCurrentStep(5 * i)

            # Créer une couche raster aléatoire (distribution uniforme)
            alg_params = {
                "EXTENT": emprise,
                "LOWER_BOUND": bruitage_min,
                "OUTPUT_TYPE": 5,
                "PIXEL_SIZE": taillePixel,
                "TARGET_CRS": "ProjectCrs",
                "UPPER_BOUND": bruitage_max,
                "OUTPUT": aleatoire,
            }
            outputs["aleatoire"] = processing.run(
                "native:createrandomuniformrasterlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setProgressText("Itération {}/{} : Bruitage du MNT source".format(i + 1, iteration))
            feedback.setCurrentStep(5 * i + 1)
            if feedback.isCanceled():
                return {}

            # Bruitage du MNT source à l'aide du raster aléatoire créé précédemment
            alg_params = default_algCalc_params.copy()

            alg_params["INPUT_A"] = aleatoire
            alg_params["INPUT_B"] = mnt.source()
            alg_params["BAND_B"] = 1
            alg_params["FORMULA"] = "A + B"  # Explications formule complexe OAT ?
            alg_params["OUTPUT"] = MNTBruite

            outputs["CalculatriceRaster"] = processing.run(
                "gdal:rastercalculator",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setProgressText(
                "Itération {}/{} : Calcul des talwegs à partir du MNT bruité".format(i + 1, iteration)
            )
            feedback.setCurrentStep(5 * i + 2)
            if feedback.isCanceled():
                return {}

            # Calcul des talwegs
            alg_params = {
                "elevation": MNTBruite,
                "accumulation": surfacesDrainees,
                "-4": True,
                "-a": True,
                "-b": True,
                "-m": False,
                "-s": False,
                "GRASS_RASTER_FORMAT_META": "",
                "GRASS_RASTER_FORMAT_OPT": "",
                "GRASS_REGION_CELLSIZE_PARAMETER": 0,
                "GRASS_REGION_PARAMETER": None,
                "blocking": None,
                "convergence": 5,
                "depression": None,
                "disturbed_land": None,
                "flow": None,
                "max_slope_length": None,
                "memory": 300,
                "threshold": tailleMinWatershed,
            }
            outputs["Rwatershed"] = processing.run(
                "grass7:r.watershed",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setProgressText(
                "Itération {}/{} : Suppression des cellules dont la valeur drainée est inférieure au seuil".format(
                    i + 1, iteration
                )
            )
            feedback.setCurrentStep(5 * i + 3)
            if feedback.isCanceled():
                return {}

            # Suppression des cellules dont la valeur drainée est inférieure au seuil
            alg_params = default_algCalc_params.copy()

            alg_params["INPUT_A"] = surfacesDrainees
            alg_params["FORMULA"] = "(A > {seuil}) * A + (A <= {seuil}) * 0".format(seuil=seuil)
            alg_params["OUTPUT"] = surfacesDraineesSeuil

            outputs["CalculatriceRaster"] = processing.run(
                "gdal:rastercalculator",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setProgressText(
                "Itération {}/{} : Calcul des maximums des cellules drainées".format(i + 1, iteration)
            )
            feedback.setCurrentStep(5 * i + 4)
            if feedback.isCanceled():
                return {}

            # Initialisation de variables pour utilisation à l'itération suivante
            if i == 0:
                surfacesDraineesSeuilMax_iterPrec = surfacesDraineesSeuil

            elif i == iteration - 1:
                alg_params = default_algCalc_params.copy()

                alg_params["INPUT_A"] = surfacesDraineesSeuil
                alg_params["INPUT_B"] = surfacesDraineesSeuilMax_iterPrec
                alg_params["BAND_B"] = 1
                alg_params["FORMULA"] = "(greater_equal(A, B)) * A + (greater(B, A)) * B"
                alg_params["OUTPUT"] = mntExzeco

                outputs["CalculatriceRaster"] = processing.run(
                    "gdal:rastercalculator",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

                # Cas particulier de la suppression des fichiers intermédiaires
                if supprFichiersIntermed:
                    self.suppressionFichier(surfacesDraineesSeuilMax_iterPrec, outputs, context, feedback)

            else:
                alg_params = default_algCalc_params.copy()

                alg_params["INPUT_A"] = surfacesDraineesSeuil
                alg_params["INPUT_B"] = surfacesDraineesSeuilMax_iterPrec
                alg_params["BAND_B"] = 1
                alg_params["FORMULA"] = "(greater_equal(A, B)) * A + (greater(B, A)) * B"
                alg_params["OUTPUT"] = surfacesDraineesSeuilMax

                outputs["CalculatriceRaster"] = processing.run(
                    "gdal:rastercalculator",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

                # Cas particulier de la suppression des fichiers intermédiaires
                if supprFichiersIntermed:
                    self.suppressionFichier(surfacesDraineesSeuilMax_iterPrec, outputs, context, feedback)

                surfacesDraineesSeuilMax_iterPrec = surfacesDraineesSeuilMax

            # Suppression des fichiers intermédaires si le paramètre est coché (coché par défaut)
            if supprFichiersIntermed:
                self.suppressionFichier(aleatoire, outputs, context, feedback)
                self.suppressionFichier(MNTBruite, outputs, context, feedback)
                self.suppressionFichier(surfacesDrainees, outputs, context, feedback)
                if i > 0:
                    self.suppressionFichier(surfacesDraineesSeuil, outputs, context, feedback)

        return {self.OUTPUT: mntExzeco}

    ## Définition de la fonction pour effacer les fichiers intermédaires
    # L'utilisation de os.remove() n'est pas possible en cours d'exécution,
    # l'astuce est de repasser sur les fichiers en créant un raster aléatoire de petite taille.
    def suppressionFichier(self, fichier, outputs, context, feedback):
        alg_params = {
            "EXTENT": "-1.0000,1.0000,-1.0000,1.0000 [EPSG:2154]",
            "LOWER_BOUND": 0.01,
            "OUTPUT_TYPE": 5,
            "PIXEL_SIZE": 1,
            "TARGET_CRS": "ProjectCrs",
            "UPPER_BOUND": 0.01,
            "OUTPUT": fichier,
        }
        outputs["aleatoire"] = processing.run(
            "native:createrandomuniformrasterlayer",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=False,
        )


# Définition des paramètres par défaut pour l'alg calculatrice raster
default_algCalc_params = {
    "BAND_A": 1,
    "BAND_B": None,
    "BAND_C": None,
    "BAND_D": None,
    "BAND_E": None,
    "BAND_F": None,
    "EXTRA": "--co COMPRESS=LZW --co PREDICTOR=3 --co ZLEVEL=9 --overwrite",
    "FORMULA": "",  # Doit obligatoirement être défini après la copie
    "INPUT_A": "",  # Doit obligatoirement être défini après la copie
    "INPUT_B": None,
    "INPUT_C": None,
    "INPUT_D": None,
    "INPUT_E": None,
    "INPUT_F": None,
    "NO_DATA": -9999,
    "OPTIONS": "",
    "RTYPE": 5,
    "OUTPUT": "",  # Doit obligatoirement être défini après la copie
}
