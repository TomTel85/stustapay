package de.stustapay.stustapay.ui.chipscan

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.Card
import androidx.compose.material.Icon
import androidx.compose.material.MaterialTheme
import androidx.compose.material.Text
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.ArrowForward
import androidx.compose.material.icons.filled.NearMe
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.stustapay.stustapay.R

/**
 * Enhanced NFC scan content with better visual cues for users
 */
@Composable
fun EnhancedNfcScanContent(
    isIminFalcons2: Boolean,
    scanStatus: String
) {
    // Pulsing animation for the NFC icon
    val infiniteTransition = rememberInfiniteTransition()
    val pulseAnimation by infiniteTransition.animateFloat(
        initialValue = 0.8f,
        targetValue = 1.2f,
        animationSpec = infiniteRepeatable(
            animation = tween(800),
            repeatMode = RepeatMode.Reverse
        )
    )
    
    // Create an animated alpha for the arrows to create a "flowing" effect
    val arrowsAlpha by infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue = 1.0f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000),
            repeatMode = RepeatMode.Reverse
        )
    )
    
    Card(
        modifier = Modifier
            .padding(8.dp)
            .fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        elevation = 8.dp
    ) {
        Column(
            modifier = Modifier
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // Header text - different for Falcon 2
            Text(
                text = if (isIminFalcons2) "Chip hier vorhalten" else "Scan a Chip",
                fontWeight = FontWeight.Bold,
                fontSize = 24.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(bottom = 16.dp)
            )
            
            // Main visual container
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                contentAlignment = Alignment.Center
            ) {
                // NFC Icon with pulse animation
                Icon(
                    imageVector = Icons.Filled.NearMe,
                    contentDescription = "NFC",
                    modifier = Modifier
                        .size(80.dp)
                        .scale(pulseAnimation)
                        .alpha(0.9f),
                    tint = MaterialTheme.colors.primary
                )
                
                // Touch icon to indicate user action
                Icon(
                    imageVector = Icons.Filled.TouchApp,
                    contentDescription = "Touch",
                    modifier = Modifier
                        .align(
                            if (isIminFalcons2) Alignment.CenterStart else Alignment.Center
                        )
                        .padding(start = if (isIminFalcons2) 8.dp else 0.dp)
                        .size(40.dp),
                    tint = MaterialTheme.colors.secondary
                )
                
                // Directional arrows for Falcon 2 devices (pointing left)
                if (isIminFalcons2) {
                    Row(
                        modifier = Modifier
                            .align(Alignment.CenterStart)
                            .alpha(arrowsAlpha),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Multiple arrows pointing left
                        repeat(3) { index ->
                            Icon(
                                imageVector = Icons.Filled.ArrowForward,
                                contentDescription = "Arrow",
                                modifier = Modifier
                                    .size(24.dp)
                                    .rotate(180f) // Rotate to point left
                                    .alpha(1f - (index * 0.2f)), // Fade out as they go further
                                tint = MaterialTheme.colors.secondary
                            )
                        }
                    }
                }
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Visual chip indicator
            Box(
                modifier = Modifier
                    .size(width = 120.dp, height = 60.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(Color(0xFFEEEEEE))
                    .border(
                        width = 2.dp,
                        color = MaterialTheme.colors.primary,
                        shape = RoundedCornerShape(8.dp)
                    )
                    .padding(8.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "NFC Chip",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color.DarkGray
                )
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Status text
            Text(
                text = scanStatus,
                fontSize = 16.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 8.dp)
            )
        }
    }
} 